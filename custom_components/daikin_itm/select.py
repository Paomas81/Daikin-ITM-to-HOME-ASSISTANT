"""Blocchi del comando a filo (Avvio/Arresto, Modo, Setpoint) come entità di configurazione."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ItmConfigEntry
from .api import RC_LOCKS
from .limits_entity import ItmLimitEntity


async def async_setup_entry(hass: HomeAssistant, entry: ItmConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ItmLockSelect(coordinator, u, "lock", which)
        for u in coordinator.data.values()
        if u.is_climate
        for which in RC_LOCKS
    )


class ItmLockSelect(ItmLimitEntity, SelectEntity):
    _attr_icon = "mdi:lock-outline"

    @property
    def options(self) -> list[str]:
        return list(RC_LOCKS[self._field][1])

    @property
    def current_option(self) -> str | None:
        lim = self.limits
        return getattr(lim, f"lock_{self._field}") if lim else None

    async def async_select_option(self, option: str) -> None:
        await self._write(
            option,
            self.coordinator.client.async_set_lock(self._group, self._name, self._field, option),
        )
