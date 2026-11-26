"""Coordinator: un ciclo di login, lettura e logout ogni DEFAULT_SCAN_INTERVAL secondi."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ItmAuthError, ItmBusyError, ItmClient, ItmError, Limits, Unit
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, LIMITS_INTERVAL, REFRESH_AFTER_COMMAND

_LOGGER = logging.getLogger(__name__)


class ItmCoordinator(DataUpdateCoordinator[dict[str, Unit]]):
    """Legge tutte le unità dell'iTM. I dati sono indicizzati per "gruppo/nome"."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ItmClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.client = client
        self.busy = False
        # Limiti di setpoint: letti solo per le unità con almeno un'entità limite attiva
        self.limits: dict[str, Limits] = {}
        self.limit_units: dict[str, int] = {}  # chiave unità -> numero di entità limite attive
        self.limits_due = False
        self._limits_read_at = 0.0
        self._cancel_refresh: Callable[[], None] | None = None

    async def _async_update_data(self) -> dict[str, Unit]:
        try:
            units = await self.client.async_get_units()
        except ItmBusyError as err:
            self.busy = True
            if self.data:
                # qualcuno sta usando il portale: teniamo gli ultimi valori e riproviamo al prossimo giro
                _LOGGER.info("Portale iTM occupato, lettura rimandata")
                return self.data
            raise UpdateFailed(str(err)) from err
        except ItmAuthError as err:
            raise UpdateFailed(f"Credenziali iTM rifiutate: {err}") from err
        except ItmError as err:
            raise UpdateFailed(str(err)) from err
        self.busy = False
        data = {u.key: u for u in units}
        await self._maybe_read_limits(data)
        return data

    async def _maybe_read_limits(self, data: dict[str, Unit]) -> None:
        wanted = [k for k, n in self.limit_units.items() if n > 0 and k in data]
        if not wanted:
            return
        stale = time.monotonic() - self._limits_read_at > LIMITS_INTERVAL
        if not (self.limits_due or stale or any(k not in self.limits for k in wanted)):
            return
        try:
            self.limits.update(await self.client.async_get_limits([(data[k].group, data[k].name) for k in wanted]))
        except ItmError as err:
            _LOGGER.info("Lettura limiti setpoint rimandata: %s", err)
            return
        self.limits_due = False
        self._limits_read_at = time.monotonic()

    def register_limits(self, key: str, delta: int) -> None:
        """Chiamato dalle entità limite quando vengono aggiunte (+1) o rimosse (-1)."""
        self.limit_units[key] = max(0, self.limit_units.get(key, 0) + delta)
        if delta > 0 and key not in self.limits:
            self.limits_due = True
            self.hass.async_create_task(self.async_request_refresh())

    async def async_command(self, command: Awaitable, optimistic: Callable[[], None]) -> None:
        """Esegue un comando, aggiorna subito lo stato in modo ottimistico e rilegge dopo qualche secondo."""
        try:
            await command
        except ItmBusyError as err:
            raise HomeAssistantError(
                "Portale iTM occupato: qualcuno è collegato dal browser, riprova tra poco"
            ) from err
        except ItmError as err:
            raise HomeAssistantError(str(err)) from err
        optimistic()
        self.async_update_listeners()
        if self._cancel_refresh:
            self._cancel_refresh()
        self._cancel_refresh = async_call_later(self.hass, REFRESH_AFTER_COMMAND, self._delayed_refresh)

    async def _delayed_refresh(self, _now) -> None:
        self._cancel_refresh = None
        await self.async_refresh()
