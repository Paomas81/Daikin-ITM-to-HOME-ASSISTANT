"""Base comune: ogni unità dell'iTM è un dispositivo in Home Assistant."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Unit
from .const import DOMAIN
from .coordinator import ItmCoordinator


class ItmUnitEntity(CoordinatorEntity[ItmCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ItmCoordinator, unit: Unit, suffix: str) -> None:
        super().__init__(coordinator)
        self._key = unit.key
        self._group = unit.group
        self._name = unit.name
        hub = coordinator.config_entry.unique_id
        self._attr_unique_id = f"{hub}_{unit.key}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{hub}_{unit.key}")},
            name=unit.name,
            manufacturer="Daikin",
            model="Unità interna VRV" if unit.is_climate else "Ventilazione (VAM)",
            via_device=(DOMAIN, hub),
        )

    @property
    def unit(self) -> Unit | None:
        return self.coordinator.data.get(self._key) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self.unit is not None
