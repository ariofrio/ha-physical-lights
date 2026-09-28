"""Physical Lights combines daylight references and calibrated light proxies."""

from homeassistant.core import HomeAssistant

from .calibrated import runtime as calibrated
from .daylight import runtime as daylight
from .melanopic import runtime as melanopic

DOMAIN = "physical_lights"
KIND_DAYLIGHT = "daylight"
KIND_CALIBRATED = "calibrated"
KIND_MELANOPIC = "melanopic"
RUNTIMES = {
    KIND_DAYLIGHT: daylight,
    KIND_CALIBRATED: calibrated,
    KIND_MELANOPIC: melanopic,
}


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the calculation actions and preview view."""
    return await daylight.async_setup(hass, config)


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    return await RUNTIMES[entry.data["kind"]].async_setup_entry(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    return await RUNTIMES[entry.data["kind"]].async_unload_entry(hass, entry)
