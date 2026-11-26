"""Configurazione da interfaccia: IP, utente e password dell'iTM."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ItmAuthError, ItmBusyError, ItmClient, ItmError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, MIN_SCAN_INTERVAL

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ItmConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ItmOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()
            client = ItmClient(
                async_get_clientsession(self.hass),
                user_input[CONF_HOST],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                zones = await client.async_get_units()
            except ItmBusyError:
                errors["base"] = "busy"
            except ItmAuthError:
                errors["base"] = "invalid_auth"
            except ItmError:
                errors["base"] = "cannot_connect"
            else:
                if not zones:
                    errors["base"] = "no_zones"
                else:
                    return self.async_create_entry(title=f"Daikin iTM {user_input[CONF_HOST]}", data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)


class ItmOptionsFlow(OptionsFlow):
    """Opzioni: intervallo di lettura."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600))}
            ),
        )
