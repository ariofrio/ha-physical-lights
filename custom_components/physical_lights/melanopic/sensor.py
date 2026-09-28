"""Estimated actual lamp-only melanopic EDI."""

from homeassistant.components.sensor import SensorEntity, SensorStateClass

from .const import DOMAIN
from .entity import MelanopicEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([EstimatedEdi(hass.data[DOMAIN][entry.entry_id])])


class EstimatedEdi(MelanopicEntity, SensorEntity):
    _attr_name = "Estimated melanopic EDI"
    _attr_icon = "mdi:weather-sunny"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "lx"
    _attr_suggested_display_precision = 1

    def __init__(self, controller) -> None:
        super().__init__(controller, "estimated_edi")

    @property
    def available(self) -> bool:
        return self.controller.estimated_edi() is not None

    @property
    def native_value(self) -> float | None:
        value = self.controller.estimated_edi()
        return None if value is None else round(value, 2)
