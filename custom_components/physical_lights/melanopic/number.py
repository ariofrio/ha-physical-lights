"""Requested EDI and CCT-flexibility controls."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .entity import MelanopicEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TargetEdi(controller), MaximumCctAdjustment(controller)])


class TargetEdi(MelanopicEntity, NumberEntity):
    _attr_name = "Target melanopic EDI"
    _attr_icon = "mdi:weather-sunny"
    _attr_native_unit_of_measurement = "lx"
    _attr_native_min_value = 0
    _attr_native_step = 0.1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, controller) -> None:
        super().__init__(controller, "target_edi")

    @property
    def native_max_value(self) -> float:
        try:
            capacity = self.controller.plan().max_edi
        except ValueError:
            capacity = 0
        return round(max(250, capacity, self.controller.target_edi), 1)

    @property
    def native_value(self) -> float:
        return round(self.controller.target_edi, 1)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.set_target(value)


class MaximumCctAdjustment(MelanopicEntity, NumberEntity):
    _attr_name = "Maximum CCT adjustment"
    _attr_icon = "mdi:thermometer-auto"
    _attr_native_unit_of_measurement = "K"
    _attr_native_min_value = 0
    _attr_native_max_value = 3800
    _attr_native_step = 100
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller) -> None:
        super().__init__(controller, "maximum_cct_adjustment")

    @property
    def native_value(self) -> float:
        return self.controller.max_delta

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.set_max_delta(round(value))
