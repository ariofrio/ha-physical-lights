"""Current reference sensors; arbitrary inputs are available through actions."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION

SENSORS = (
    SensorEntityDescription(
        key="lux",
        name="Illuminance",
        native_unit_of_measurement="lx",
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:white-balance-sunny",
    ),
    SensorEntityDescription(
        key="melanopic_edi",
        name="Melanopic EDI",
        native_unit_of_measurement="lx",
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:weather-sunny",
    ),
    SensorEntityDescription(
        key="cct_kelvin",
        name="Color temperature",
        native_unit_of_measurement="K",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:temperature-kelvin",
    ),
    SensorEntityDescription(
        key="daylight_level",
        name="Level",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        icon="mdi:brightness-6",
    ),
    SensorEntityDescription(
        key="geometric_elevation",
        name="Geometric solar elevation",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:sun-angle",
    ),
    SensorEntityDescription(
        key="noon_elevation",
        name="Noon solar elevation",
        native_unit_of_measurement="°",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:weather-sunny",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        DaylightSensor(entry.runtime_data, entry.entry_id, entry.title, desc) for desc in SENSORS
    )


class DaylightSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id, entry_title, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=entry_title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Physical Lights",
            model="Fixed-atmosphere solar reference",
            sw_version=VERSION,
        )

    @property
    def native_value(self):
        return self.coordinator.data[self.entity_description.key]

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        keys = ("model", "quality", "cct_reason", "relative_lux_spread", "uv_spread")
        attrs = {key: data[key] for key in keys}
        if self.entity_description.key in ("lux", "melanopic_edi", "cct_kelvin"):
            attrs.update(
                receiver_tilt=data["receiver_tilt"],
                receiver_facing_mode=data["receiver_facing_mode"],
                receiver_bearing=data["receiver_bearing"],
                orientation_model=data["orientation_model"],
            )
        if self.entity_description.key == "lux":
            attrs.update(xy=data["xy"], xyz=data["xyz"], duv=data["duv"])
        if self.entity_description.key == "melanopic_edi":
            attrs.update(
                melanopic_edi_reason=data["melanopic_edi_reason"],
                relative_melanopic_spread=data["relative_melanopic_spread"],
                spectral_reference="CIE S 026:2018 / D65",
            )
        if self.entity_description.key in ("daylight_level", "noon_elevation"):
            attrs["solar_noon"] = data["solar_noon"]
        return attrs
