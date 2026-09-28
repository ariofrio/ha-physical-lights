"""Estimated actual lamp contribution at the calibrated position."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass

from .const import DOMAIN
from .entity import ProxyEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([EstimatedIlluminance(hass.data[DOMAIN][entry.entry_id])])


class EstimatedIlluminance(ProxyEntity, SensorEntity):
    _attr_name = "Estimated illuminance"
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "lx"
    _attr_suggested_display_precision = 1

    def __init__(self, controller) -> None:
        super().__init__(controller, "estimated_illuminance")

    @property
    def available(self) -> bool:
        return self.controller.estimated_lux() is not None

    @property
    def native_value(self) -> float | None:
        value = self.controller.estimated_lux()
        return None if value is None else round(value, 2)
