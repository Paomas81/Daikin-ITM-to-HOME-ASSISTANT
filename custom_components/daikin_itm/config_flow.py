"""Configurazione da interfaccia: IP, utente e password dell'iTM."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ItmAuthError, ItmBusyError, ItmClient, ItmError
from .const import DOMAIN

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ItmConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
