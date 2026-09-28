"""Preferred-color light control with brightness mapped to melanopic EDI."""

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)

from .const import DOMAIN
from .entity import MelanopicEntity
from .spectral import MAX_KELVIN, MIN_KELVIN


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([MelanopicLight(hass.data[DOMAIN][entry.entry_id])])


class MelanopicLight(MelanopicEntity, LightEntity):
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_min_color_temp_kelvin = MIN_KELVIN
    _attr_max_color_temp_kelvin = MAX_KELVIN

    def __init__(self, controller) -> None:
        super().__init__(controller, "light")

    @property
    def available(self) -> bool:
        source = self.controller.hass.states.get(self.controller.source_entity_id)
        return (
            self.controller.source() is not None
            and source is not None
            and source.state not in ("unknown", "unavailable")
        )

    @property
    def is_on(self) -> bool:
        return self.controller.is_on()

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.COLOR_TEMP

    @property
    def color_temp_kelvin(self) -> int:
        return self.controller.preferred_kelvin

    @property
    def brightness(self) -> int | None:
        try:
            return self.controller.display_brightness()
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict:
        source = self.controller.source()
        try:
            clipped = self.controller.plan().clipped
        except ValueError:
            clipped = None
        return {
            "source_entity_id": self.controller.source_entity_id,
            "requested_melanopic_edi_lx": round(self.controller.target_edi, 2),
            "source_reported_color_temperature_kelvin": source.reported_kelvin()
            if source
            else None,
            "target_clipped": clipped,
        }

    async def async_turn_on(self, **kwargs) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        transition = kwargs.get(ATTR_TRANSITION)
        if brightness is not None:
            await self.controller.set_brightness(brightness, kelvin, transition)
        elif kelvin is not None:
            await self.controller.set_preferred(kelvin, transition)
        else:
            await self.controller.turn_on(transition)

    async def async_turn_off(self, **kwargs) -> None:
        await self.controller.turn_off(kwargs.get(ATTR_TRANSITION))
