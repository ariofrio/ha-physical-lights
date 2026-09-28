"""Requested and reference illuminance controls."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .entity import ProxyEntity
from .model import A23


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TargetIlluminance(controller), ReferenceIlluminance(controller)])


class TargetIlluminance(ProxyEntity, NumberEntity):
    _attr_name = "Target illuminance"
    _attr_icon = "mdi:brightness-6"
    _attr_native_unit_of_measurement = "lx"
    _attr_native_min_value = 0
    _attr_native_step = 0.1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, controller) -> None:
        super().__init__(controller, "target_illuminance")

    @property
    def native_max_value(self) -> float:
        return round(
            max(
                1,
                self.controller.target_lux,
                A23.lux(100, 4003, self.controller.reference_lux),
            ),
            1,
        )

    @property
    def native_value(self) -> float:
        return round(self.controller.target_lux, 1)

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.set_target(value)


class ReferenceIlluminance(ProxyEntity, NumberEntity):
    _attr_name = "Reference illuminance"
    _attr_icon = "mdi:lightbulb-on-outline"
    _attr_native_unit_of_measurement = "lx"
    _attr_native_min_value = 0.1
    _attr_native_max_value = 100000
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, controller) -> None:
        super().__init__(controller, "reference_illuminance")

    @property
    def native_value(self) -> float:
        return self.controller.reference_lux

    async def async_set_native_value(self, value: float) -> None:
        await self.controller.set_reference(value)
