"""Base per le entità dei limiti di setpoint: configurazione, disattivate di default."""
from __future__ import annotations

from homeassistant.const import EntityCategory

from .api import Limits, Unit
from .coordinator import ItmCoordinator
from .entity import ItmUnitEntity


class ItmLimitEntity(ItmUnitEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: ItmCoordinator, unit: Unit, kind: str, field: str) -> None:
        super().__init__(coordinator, unit, f"limit_{kind}_{field}")
        self._kind = kind
        self._field = field
        self._attr_translation_key = f"limit_{kind}_{field}"

    @property
    def limits(self) -> Limits | None:
        return self.coordinator.limits.get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self.limits is not None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.register_limits(self._key, +1)

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.register_limits(self._key, -1)
        await super().async_will_remove_from_hass()

    async def _write(self, value) -> None:
        lim = self.limits

        def optimistic() -> None:
            if lim is not None:
                setattr(lim, f"{self._kind}_{self._field}", value)
            # i limiti cambiano il range del setpoint: rileggiamo anche loro
            self.coordinator.limits_due = True

        await self.coordinator.async_command(
            self.coordinator.client.async_set_limit(self._group, self._name, self._kind, self._field, value),
            optimistic,
        )
