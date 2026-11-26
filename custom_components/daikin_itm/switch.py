"""Interruttori per le unità senza setpoint (ventilazione VAM): solo Avvia/Arresta."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ItmConfigEntry
from .entity import ItmUnitEntity


async def async_setup_entry(hass: HomeAssistant, entry: ItmConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ItmVentSwitch(coordinator, u) for u in coordinator.data.values() if not u.is_climate)


class ItmVentSwitch(ItmUnitEntity, SwitchEntity):
    _attr_name = None
    _attr_icon = "mdi:hvac"

    def __init__(self, coordinator, unit) -> None:
        super().__init__(coordinator, unit, "switch")

    @property
    def is_on(self) -> bool | None:
        u = self.unit
        return u.on if u else None

    async def _set(self, on: bool) -> None:
        u = self.unit
        if u is None:
            return
        def optimistic() -> None:
            u.on = on
        await self.coordinator.async_command(
            self.coordinator.client.async_set_power(self._group, self._name, on), optimistic
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
