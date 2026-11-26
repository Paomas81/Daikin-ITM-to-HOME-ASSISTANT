"""Sensore della temperatura letta dall'unità (mandata), uno per unità interna."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ItmConfigEntry
from .entity import ItmUnitEntity


async def async_setup_entry(hass: HomeAssistant, entry: ItmConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ItmSupplyTemp(coordinator, u) for u in coordinator.data.values() if u.is_climate)


class ItmSupplyTemp(ItmUnitEntity, SensorEntity):
    _attr_translation_key = "supply_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, unit) -> None:
        super().__init__(coordinator, unit, "supply_temperature")

    @property
    def native_value(self) -> float | None:
        u = self.unit
        return u.temperature if u else None
