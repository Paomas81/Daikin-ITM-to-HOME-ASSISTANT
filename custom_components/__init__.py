"""Integrazione Daikin intelligent Touch Manager (iTM) tramite il portale web."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ItmClient
from .const import DOMAIN
from .coordinator import ItmCoordinator

PLATFORMS = [Platform.CLIMATE, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]

type ItmConfigEntry = ConfigEntry[ItmCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ItmConfigEntry) -> bool:
    client = ItmClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = ItmCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    # dispositivo "padre" per l'iTM; ogni unità è un dispositivo collegato a questo
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        name=entry.title,
        manufacturer="Daikin",
        model="intelligent Touch Manager",
        sw_version="Ver1.20.00",
        configuration_url=f"http://{entry.data[CONF_HOST]}/",
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ItmConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ItmConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
