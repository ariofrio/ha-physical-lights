"""Sensor platform for Physical Lights devices."""

from . import KIND_CALIBRATED, KIND_DAYLIGHT, KIND_MELANOPIC
from .calibrated import sensor as calibrated
from .daylight import sensor as daylight
from .melanopic import sensor as melanopic

PLATFORMS = {
    KIND_DAYLIGHT: daylight,
    KIND_CALIBRATED: calibrated,
    KIND_MELANOPIC: melanopic,
}


async def async_setup_entry(hass, entry, async_add_entities):
    await PLATFORMS[entry.data["kind"]].async_setup_entry(hass, entry, async_add_entities)
