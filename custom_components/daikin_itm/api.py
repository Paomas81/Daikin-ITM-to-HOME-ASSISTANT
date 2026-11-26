"""Client per il protocollo web dell'intelligent Touch Manager Daikin (firmware Ver1.20.00).

Il portale web è un'applicazione Flash "thin client": l'iTM disegna l'interfaccia lato
server e il client manda solo eventi sui widget. Ogni messaggio è una POST a /cmd/ con
il parametro snD= in esadecimale:

  contatore(8) loginID(4) screenID(4) partID(4) eventType(4) eventDataType(4)
  numEventData(8) lunghezzaArray(4) lunghezzaStringa(4) [dati]

Le risposte sono "delta": contengono solo i widget cambiati rispetto a ciò che il
client mostra, quindi lo stato va accumulato per tutta la sessione.

L'iTM accetta un solo accesso web alla volta: ogni operazione fa login, lavora e
fa logout, così il portale resta libero per le persone.

Navigazione: Alto -> "Tutto" -> Giù -> gruppi (es. "U/I", "Ventilatore") -> Giù -> unità.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

import aiohttp

_LOGGER = logging.getLogger(__name__)

HELLO = "ffffffffffffffffffff00000002ffffffff0000000aVer1.20.00"
PRESS = 0xFFFFFFFF  # valore degli eventi "pulsante premuto"

# Schermata principale
SCREEN_MAIN = 0x0001
PART_ALTO = 0x0001
PART_GIU = 0x0002
PART_LIST = 0x0006
# Finestra operazioni (a destra)
SCREEN_OPER = 0x0004
PART_ONOFF = 0x0009      # tendina Avvia/Arresta: 0 = Avvia, 1 = Arresta (chiede conferma)
PART_SETPOINT = 0x000B   # tendina setpoint: indice nella lista dei valori ammessi
PART_FAN_UP = 0x000F
PART_FAN_DOWN = 0x0010   # gira in tondo: 1 tacca -> massimo
PART_DETAILS = 0x0011    # "Impost." -> impostazioni dettagliate (schermata 7)
# Impostazioni dettagliate
SCREEN_DETAIL = 0x0007
PART_TABS = 0x0001
TAB_AC = 2
PART_MODE_CHECK = 0x0011
PART_MODE_LIST = 0x0012
PART_OK = 0x0005

# icona velocità -> (tacche attuali, tacche totali dell'unità)
FAN_ICONS = {
    0x0BBB: (1, 2), 0x0BBD: (2, 2),               # unità a 2 velocità
    0x0BC1: (1, 3), 0x0BC3: (2, 3), 0x0BC5: (3, 3),  # unità a 3 velocità
}

RE_LIST = re.compile(r"00060578([0-9a-f]{8})")
RE_SP_LIST = re.compile(r"000b01f5([0-9a-f]{8})")
RE_ONOFF = re.compile(r"00090190([0-9a-f]{8})")
RE_SP_IDX = re.compile(r"000b0190([0-9a-f]{8})")
RE_FAN = re.compile(r"000e03e8([0-9a-f]{8})")
RE_TEMP = re.compile(r"000400c8([0-9a-f]{4})")
RE_MODE = re.compile(r"000500c8([0-9a-f]{4})")
RE_MODE_LIST = re.compile(r"001201f4([0-9a-f]{8})")
RE_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

REQUEST_PAUSE = 0.3  # secondi tra una richiesta e l'altra, per non stressare l'iTM


class ItmError(Exception):
    """Errore generico di comunicazione con l'iTM."""


class ItmAuthError(ItmError):
    """Credenziali rifiutate."""


class ItmBusyError(ItmError):
    """Qualcuno è già collegato al portale (l'iTM accetta una sola sessione)."""


@dataclass
class Unit:
    """Stato di un'unità (interna o VAM) come letto dalla finestra operazioni."""

    group: str
    name: str
    on: bool | None = None
    setpoints: list[int] = field(default_factory=list)
    setpoint_index: int | None = None
    fan_icon: int | None = None
    mode: str | None = None
    temperature: float | None = None  # temperatura letta dall'unità (mandata)

    @property
    def key(self) -> str:
        return f"{self.group}/{self.name}"

    @property
    def is_climate(self) -> bool:
        """Le unità con setpoint sono climatizzatori, le altre (VAM) solo on/off."""
        return bool(self.setpoints)

    @property
    def target(self) -> int | None:
        if self.setpoint_index is None or self.setpoint_index >= len(self.setpoints):
            return None
        return self.setpoints[self.setpoint_index]

    @property
    def fan_level(self) -> int | None:
        return FAN_ICONS[self.fan_icon][0] if self.fan_icon in FAN_ICONS else None

    @property
    def fan_steps(self) -> int | None:
        return FAN_ICONS[self.fan_icon][1] if self.fan_icon in FAN_ICONS else None


def _h4(n: int) -> str:
    return f"{n & 0xFFFF:04x}"


def _h8(n: int) -> str:
    return f"{n & 0xFFFFFFFF:08x}"


def parse_list(resp: str) -> list[tuple[str, int, int]]:
    """Estrae (nome, icona, stato) dalla lista elementi (widget 0006). Stato 0 = acceso."""
    m = RE_LIST.search(resp)
    if not m:
        return []
    count, pos, items = int(m.group(1), 16), m.end(), []
    for _ in range(count):
        n = int(resp[pos:pos + 4], 16)
        name = resp[pos + 4:pos + 4 + n]
        pos += 4 + n
        items.append((name, int(resp[pos:pos + 4], 16), int(resp[pos + 4:pos + 8], 16)))
        pos += 8
    return items


def parse_strings(resp: str, m: re.Match) -> list[str]:
    """Legge una lista di stringhe [conteggio(8)] [len(4) testo]..."""
    count, pos, out = int(m.group(1), 16), m.end(), []
    for _ in range(count):
        n = int(resp[pos:pos + 4], 16)
        out.append(resp[pos + 4:pos + 4 + n])
        pos += 4 + n
    return out


class PanelState:
    """Copia di ciò che il portale mostra nella finestra operazioni."""

    def __init__(self) -> None:
        self.onoff: int | None = None
        self.sp_list: list[int] = []
        self.sp_idx: int | None = None
        self.fan: int | None = None
        self.mode: str | None = None
        self.temp: float | None = None

    def update(self, resp: str) -> None:
        if m := RE_SP_LIST.search(resp):
            c, s = int(m.group(1), 16), m.end()
            self.sp_list = [int(resp[s + 8 * i:s + 8 * i + 8], 16) for i in range(c)]
        if m := RE_ONOFF.search(resp):
            self.onoff = int(m.group(1), 16)
        if m := RE_SP_IDX.search(resp):
            self.sp_idx = int(m.group(1), 16)
        if m := RE_FAN.search(resp):
            self.fan = int(m.group(1), 16)
        # I testi si leggono solo dal blocco della finestra operazioni (schermata 4):
        # gli stessi numeri di widget compaiono anche nella barra menu ("Lock", "Logoff").
        seg_at = resp.rfind("00030004")
        if seg_at < 0:
            return
        seg = resp[seg_at:]
        if m := RE_TEMP.search(seg):
            text = seg[m.end():m.end() + int(m.group(1), 16)]
            if n := RE_NUMBER.search(text):
                self.temp = float(n.group())
        if m := RE_MODE.search(seg):
            self.mode = seg[m.end():m.end() + int(m.group(1), 16)]


class ItmClient:
    """Client asincrono per un iTM."""

    def __init__(self, session: aiohttp.ClientSession, host: str, username: str, password: str) -> None:
        self._session = session
        self._url = f"http://{host}/cmd/"
        self._referer = f"http://{host}/"
        self._username = username
        self._password = password
        self._lock = asyncio.Lock()
        self._sid: str | None = None
        self._seq = 0
        self._panel = PanelState()

    # ---------- trasporto e sessione ----------

    async def _post(self, payload: str) -> str:
        try:
            async with self._session.post(
                self._url,
                data=("snD=" + payload).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": self._referer},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                raw = await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ItmError(f"Errore di comunicazione con l'iTM: {err}") from err
        await asyncio.sleep(REQUEST_PAUSE)
        return raw.decode("utf-8", "replace").rstrip("\x00")

    async def _login(self) -> None:
        hello = await self._post(HELLO)
        hello_id = hello[12:16]
        cred = _h4(len(self._username)) + self._username + self._password
        resp = await self._post("ffffffffffff" + hello_id + "000400010002ffffffff" + _h8(len(cred)) + cred)
        if "Login impossibile" in resp or "Login failed" in resp:
            if "collegato" in resp.lower() or "already" in resp.lower():
                raise ItmBusyError("Portale iTM occupato: c'è già una sessione attiva")
            raise ItmAuthError("Login rifiutato dall'iTM")
        if not RE_LIST.search(resp):
            raise ItmError("Risposta di login non riconosciuta")
        self._sid = resp[20:24]
        self._seq = 0
        self._panel = PanelState()
        self._panel.update(resp)

    async def _logout(self) -> None:
        if self._sid is None:
            return
        try:
            await self._post("ffffffff" + self._sid + "ffffffff000a0000ffffffff00000000")
        except ItmError as err:
            _LOGGER.warning("Logout iTM non riuscito: %s", err)
        finally:
            self._sid = None

    async def _event(self, screen: int, part: int, ev_type: int, data_type: int, value: int) -> str:
        resp = await self._post(
            _h8(self._seq) + self._sid + _h4(screen) + _h4(part) + _h4(ev_type) + _h4(data_type) + _h8(value) + "00000000"
        )
        self._seq += 1
        self._panel.update(resp)
        return resp

    async def _press(self, screen: int, part: int) -> str:
        return await self._event(screen, part, 1, 0, PRESS)

    async def _release(self) -> None:
        """Evento che il portale manda dopo ogni azione nella finestra operazioni."""
        await self._event(SCREEN_OPER, 0xFFFF, 3, 0, PRESS)

    # ---------- navigazione ----------

    async def _select(self, index: int) -> str:
        return await self._event(SCREEN_MAIN, PART_LIST, 1, 1, index)

    async def _open_groups(self) -> list[tuple[str, int, int]]:
        """Dalla cima: seleziona "Tutto" e scende, restituisce i gruppi (U/I, Ventilatore...)."""
        await self._press(SCREEN_MAIN, PART_ALTO)
        await self._select(0)
        return parse_list(await self._press(SCREEN_MAIN, PART_GIU))

    async def _open_group(self, groups: list, group: str) -> list[tuple[str, int, int]]:
        names = [g[0] for g in groups]
        if group not in names:
            raise ItmError(f"Gruppo '{group}' non trovato sull'iTM")
        await self._select(names.index(group))
        return parse_list(await self._press(SCREEN_MAIN, PART_GIU))

    async def _goto_unit(self, group: str, name: str) -> None:
        units = await self._open_group(await self._open_groups(), group)
        names = [u[0] for u in units]
        if name not in names:
            raise ItmError(f"Unità '{name}' non trovata nel gruppo '{group}'")
        await self._select(names.index(name))

    def _snapshot(self, group: str, name: str) -> Unit:
        p = self._panel
        return Unit(
            group=group,
            name=name,
            on=None if p.onoff is None else p.onoff == 0,
            setpoints=list(p.sp_list),
            setpoint_index=p.sp_idx,
            fan_icon=p.fan,
            mode=p.mode,
            temperature=p.temp,
        )

    # ---------- operazioni pubbliche ----------

    async def _in_session(self, work):
        async with self._lock:
            await self._login()
            try:
                return await work()
            finally:
                await self._logout()

    async def async_get_units(self) -> list[Unit]:
        async def work() -> list[Unit]:
            units: list[Unit] = []
            group_names = [g[0] for g in await self._open_groups()]
            for group in group_names:
                items = await self._open_group(await self._open_groups(), group)
                for idx, (name, _icon, _state) in enumerate(items):
                    await self._select(idx)
                    units.append(self._snapshot(group, name))
            return units

        return await self._in_session(work)

    async def async_set_power(self, group: str, name: str, on: bool) -> None:
        async def work() -> None:
            await self._goto_unit(group, name)
            await self._power(on)

        await self._in_session(work)

    async def _power(self, on: bool) -> None:
        resp = await self._event(SCREEN_OPER, PART_ONOFF, 1, 1, 0 if on else 1)
        # l'iTM chiede conferma ("Avvia?" / "Conf. arresto"): premiamo Sì
        if dlg := re.search(r"00060004([0-9a-f]{4})0002", resp):
            await self._press(SCREEN_OPER, int(dlg.group(1), 16))
        await self._release()

    async def async_set_setpoint(self, group: str, name: str, temperature: int) -> None:
        async def work() -> None:
            await self._goto_unit(group, name)
            sp = self._panel.sp_list
            if temperature not in sp:
                raise ItmError(f"{temperature} °C fuori dal range ammesso ({min(sp, default='?')}-{max(sp, default='?')})")
            await self._event(SCREEN_OPER, PART_SETPOINT, 1, 1, sp.index(temperature))
            await self._release()

        await self._in_session(work)

    async def async_set_fan(self, group: str, name: str, level: int) -> None:
        async def work() -> None:
            await self._goto_unit(group, name)
            for _ in range(4):
                if FAN_ICONS.get(self._panel.fan, (None,))[0] == level:
                    return
                await self._press(SCREEN_OPER, PART_FAN_DOWN)  # ciclica: dal minimo torna al massimo
                await self._release()
            raise ItmError(f"Velocità {level} non raggiunta (icona {self._panel.fan:#06x})")

        await self._in_session(work)

    async def async_set_mode(self, group: str, name: str, mode: str, power_on: bool = False) -> None:
        """Cambia il modo (testo come nel portale: "Caldo", "Freddo", "Vent") e opzionalmente accende."""

        async def work() -> None:
            await self._goto_unit(group, name)
            if self._panel.mode != mode:
                resp = await self._press(SCREEN_OPER, PART_DETAILS)
                m = RE_MODE_LIST.search(resp)
                modes = parse_strings(resp, m) if m else []
                if mode not in modes:
                    raise ItmError(f"Modo '{mode}' non disponibile per {name} (disponibili: {', '.join(modes)})")
                await self._event(SCREEN_DETAIL, PART_TABS, 8, 1, TAB_AC)
                await self._event(SCREEN_DETAIL, PART_MODE_CHECK, 1, 1, 1)
                await self._event(SCREEN_DETAIL, PART_MODE_LIST, 1, 1, modes.index(mode))
                resp = await self._press(SCREEN_DETAIL, PART_OK)
                if dlg := re.search(r"00060007([0-9a-f]{4})0002", resp):
                    await self._press(SCREEN_DETAIL, int(dlg.group(1), 16))  # "Impostare?" -> Sì
                else:
                    raise ItmError("Conferma del cambio modo non ricevuta")
                if power_on:
                    await self._goto_unit(group, name)
            if power_on and self._panel.onoff != 0:
                await self._power(True)

        await self._in_session(work)
