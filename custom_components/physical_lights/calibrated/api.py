"""Small runtime interface for integrations controlling a calibrated light."""

from collections.abc import Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .controller import Controller


class CalibratedLightPort:
    """Expose calibrated capabilities without coupling callers to bulb curves."""

    def __init__(self, controller: Controller) -> None:
        self._controller = controller

    @property
    def calibration_key(self) -> tuple[str, str, float]:
        """Change when the measured model or receiving-position scale changes."""
        controller = self._controller
        return controller.entry.entry_id, controller.model.model_id, controller.reference_lux

    @property
    def min_kelvin(self) -> int:
        return self._controller.model.min_kelvin

    @property
    def max_kelvin(self) -> int:
        return self._controller.model.max_kelvin

    def min_lux(self, kelvin: int) -> float:
        controller = self._controller
        return controller.model.lux(controller.model.min_dim, kelvin, controller.reference_lux)

    def max_lux(self, kelvin: int) -> float:
        controller = self._controller
        return controller.model.lux(controller.model.max_dim, kelvin, controller.reference_lux)

    def estimated_lux(self) -> float | None:
        return self._controller.estimated_lux()

    def reported_kelvin(self) -> int | None:
        controller = self._controller
        state = controller.source_state()
        if state is None or not controller.is_white(state):
            return None
        kelvin = state.attributes.get("color_temp_kelvin")
        return round(kelvin) if isinstance(kelvin, (int, float)) else None

    def source_state(self):
        return self._controller.source_state()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        return self._controller.subscribe(listener)

    async def async_set_output(
        self, target_lux: float, kelvin: int, transition: float | None = None
    ) -> None:
        await self._controller.set_target_and_kelvin(target_lux, kelvin, transition)


def get_calibrated_light(hass: HomeAssistant, entity_id: str) -> CalibratedLightPort | None:
    """Return the live calibrated controller behind an integration-owned light."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    if registry_entry is None or registry_entry.platform != DOMAIN:
        return None
    controller = hass.data.get(DOMAIN, {}).get(registry_entry.config_entry_id)
    if (
        controller is None
        or controller.entry.data.get("kind") != "calibrated"
        or registry_entry.unique_id != f"{controller.entry.entry_id}_light"
    ):
        return None
    return CalibratedLightPort(controller)
