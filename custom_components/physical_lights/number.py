"""Number platform for Physical Lights proxies."""

from . import KIND_CALIBRATED, KIND_MELANOPIC
from .calibrated import number as calibrated
from .melanopic import number as melanopic

PLATFORMS = {KIND_CALIBRATED: calibrated, KIND_MELANOPIC: melanopic}


async def async_setup_entry(hass, entry, async_add_entities):
    await PLATFORMS[entry.data["kind"]].async_setup_entry(hass, entry, async_add_entities)
