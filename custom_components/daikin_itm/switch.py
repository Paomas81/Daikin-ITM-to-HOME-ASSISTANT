"""Interruttori per le unità senza setpoint (ventilazione VAM): solo Avvia/Arresta."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ItmConfigEntry
from .entity import ItmUnitEntity
from .limits_entity import ItmLimitEntity


async def async_setup_entry(hass: HomeAssistant, entry: ItmConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [ItmVentSwitch(coordinator, u) for u in coordinator.data.values() if not u.is_climate]
    entities += [
        ItmLimitSwitch(coordinator, u, kind, "enabled")
        for u in coordinator.data.values()
        if u.is_climate
        for kind in ("heat", "cool")
    ]
    async_add_entities(entities)


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


class ItmLimitSwitch(ItmLimitEntity, SwitchEntity):
    """Attiva/disattiva la restrizione del setpoint (caldo o freddo)."""

    @property
    def is_on(self) -> bool | None:
        lim = self.limits
        return getattr(lim, f"{self._kind}_enabled") if lim else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write(False)
