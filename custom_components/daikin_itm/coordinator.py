"""Coordinator: un ciclo di login, lettura e logout ogni DEFAULT_SCAN_INTERVAL secondi."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ItmAuthError, ItmBusyError, ItmClient, ItmError, Unit
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, REFRESH_AFTER_COMMAND

_LOGGER = logging.getLogger(__name__)


class ItmCoordinator(DataUpdateCoordinator[dict[str, Unit]]):
    """Legge tutte le unità dell'iTM. I dati sono indicizzati per "gruppo/nome"."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ItmClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.busy = False
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
        return {u.key: u for u in units}

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
