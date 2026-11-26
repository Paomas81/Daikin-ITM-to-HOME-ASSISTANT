"""Limiti Max/Min del setpoint (caldo e freddo) come entità di configurazione."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ItmConfigEntry
from .limits_entity import ItmLimitEntity


async def async_setup_entry(hass: HomeAssistant, entry: ItmConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ItmLimitNumber(coordinator, u, kind, field)
        for u in coordinator.data.values()
        if u.is_climate
        for kind in ("heat", "cool")
        for field in ("max", "min")
    )


class ItmLimitNumber(ItmLimitEntity, NumberEntity):
    _attr_native_min_value = 16
    _attr_native_max_value = 32
    _attr_native_step = 1  # solo gradi interi: la codifica dei decimali non è verificata
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> float | None:
        lim = self.limits
        return getattr(lim, f"{self._kind}_{self._field}") if lim else None

    async def async_set_native_value(self, value: float) -> None:
        lim = self.limits
        if lim is not None:
            other = getattr(lim, f"{self._kind}_{'min' if self._field == 'max' else 'max'}")
            if other is not None and ((self._field == "max" and value < other) or (self._field == "min" and value > other)):
                raise HomeAssistantError("Il limite massimo non può essere inferiore al minimo")
        await self._write(int(round(value)))
