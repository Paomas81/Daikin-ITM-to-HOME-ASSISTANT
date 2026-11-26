"""Entità climate, una per unità interna dell'iTM."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ItmConfigEntry
from .api import FAN_ICONS
from .const import HVAC_TO_MODE, MODE_TO_HVAC
from .entity import ItmUnitEntity

# modi ventilazione di HA per numero di velocità dell'unità
FAN_MODES = {2: [FAN_LOW, FAN_HIGH], 3: [FAN_LOW, FAN_MEDIUM, FAN_HIGH]}


async def async_setup_entry(hass: HomeAssistant, entry: ItmConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ItmClimate(coordinator, u) for u in coordinator.data.values() if u.is_climate)


class ItmClimate(ItmUnitEntity, ClimateEntity):
    _attr_name = None  # entità principale del dispositivo: prende il nome dell'unità
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.FAN_ONLY]

    def __init__(self, coordinator, unit) -> None:
        super().__init__(coordinator, unit, "climate")

    @property
    def supported_features(self) -> ClimateEntityFeature:
        f = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        u = self.unit
        if u and u.fan_level is not None:
            f |= ClimateEntityFeature.FAN_MODE
        return f

    @property
    def hvac_mode(self) -> HVACMode | None:
        u = self.unit
        if u is None or u.on is None:
            return None
        if not u.on:
            return HVACMode.OFF
        hvac = MODE_TO_HVAC.get(u.mode or "")
        return HVACMode(hvac) if hvac else HVACMode.AUTO

    @property
    def target_temperature(self) -> float | None:
        u = self.unit
        return float(u.target) if u and u.target is not None else None

    @property
    def min_temp(self) -> float:
        u = self.unit
        return float(min(u.setpoints)) if u and u.setpoints else 16.0

    @property
    def max_temp(self) -> float:
        u = self.unit
        return float(max(u.setpoints)) if u and u.setpoints else 32.0

    @property
    def fan_modes(self) -> list[str] | None:
        u = self.unit
        return FAN_MODES.get(u.fan_steps) if u else None

    @property
    def fan_mode(self) -> str | None:
        u = self.unit
        if u is None or u.fan_level is None or u.fan_steps not in FAN_MODES:
            return None
        return FAN_MODES[u.fan_steps][u.fan_level - 1]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        u = self.unit
        return {
            "modo_itm": u.mode if u else None,
            "icona_ventilazione": f"{u.fan_icon:#06x}" if u and u.fan_icon is not None else None,
            "portale_occupato": self.coordinator.busy,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        u = self.unit
        if temp is None or u is None:
            return
        value = int(round(temp))

        def optimistic() -> None:
            if value in u.setpoints:
                u.setpoint_index = u.setpoints.index(value)

        await self.coordinator.async_command(
            self.coordinator.client.async_set_setpoint(self._group, self._name, value), optimistic
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        u = self.unit
        if u is None:
            return
        client = self.coordinator.client
        if hvac_mode == HVACMode.OFF:
            def optimistic() -> None:
                u.on = False
            await self.coordinator.async_command(client.async_set_power(self._group, self._name, False), optimistic)
            return
        mode = HVAC_TO_MODE.get(hvac_mode)
        if mode is None:
            raise HomeAssistantError(f"Modo {hvac_mode} non supportato")

        def optimistic_on() -> None:
            u.on = True
            u.mode = mode

        await self.coordinator.async_command(
            client.async_set_mode(self._group, self._name, mode, power_on=True), optimistic_on
        )

    async def async_turn_on(self) -> None:
        u = self.unit
        if u is None:
            return
        def optimistic() -> None:
            u.on = True
        await self.coordinator.async_command(
            self.coordinator.client.async_set_power(self._group, self._name, True), optimistic
        )

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        u = self.unit
        modes = FAN_MODES.get(u.fan_steps) if u else None
        if not modes or fan_mode not in modes:
            return
        level = modes.index(fan_mode) + 1
        icon = next(i for i, v in FAN_ICONS.items() if v == (level, u.fan_steps))

        def optimistic() -> None:
            u.fan_icon = icon

        await self.coordinator.async_command(
            self.coordinator.client.async_set_fan(self._group, self._name, level), optimistic
        )
