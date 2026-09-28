"""Calibrated light entity."""

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_FLASH,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_TRANSITION,
    ATTR_WHITE,
    ATTR_XY_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)

from .const import DOMAIN
from .entity import ProxyEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([CalibratedLight(hass.data[DOMAIN][entry.entry_id])])


class CalibratedLight(ProxyEntity, LightEntity):
    _attr_name = None

    def __init__(self, controller) -> None:
        super().__init__(controller, "light")
        self._attr_min_color_temp_kelvin = controller.model.min_kelvin
        self._attr_max_color_temp_kelvin = controller.model.max_kelvin

    @property
    def available(self) -> bool:
        source = self.controller.source_state()
        return source is not None and source.state not in ("unknown", "unavailable")

    @property
    def is_on(self) -> bool:
        source = self.controller.source_state()
        return source is not None and source.state == "on"

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        source = self.controller.source_state()
        modes = source.attributes.get("supported_color_modes", []) if source else []
        supported = {ColorMode(mode) for mode in modes if mode in ColorMode._value2member_map_}
        current = source.attributes.get("color_mode") if source else None
        if current in (ColorMode.RGB, ColorMode.RGBW, ColorMode.RGBWW, ColorMode.HS, ColorMode.XY):
            supported.add(ColorMode(current))
        return supported or {ColorMode.COLOR_TEMP}

    @property
    def supported_features(self) -> LightEntityFeature:
        source = self.controller.source_state()
        features = source.attributes.get("supported_features", 0) if source else 0
        return LightEntityFeature(features) | LightEntityFeature.TRANSITION

    @property
    def color_mode(self) -> ColorMode:
        source = self.controller.source_state()
        mode = source.attributes.get("color_mode") if source else None
        return ColorMode(mode) if mode in ColorMode._value2member_map_ else ColorMode.UNKNOWN

    @property
    def effect_list(self) -> list[str] | None:
        source = self.controller.source_state()
        return source.attributes.get("effect_list") if source else None

    @property
    def effect(self) -> str | None:
        source = self.controller.source_state()
        return source.attributes.get("effect") if source else None

    @property
    def rgbww_color(self) -> tuple[int, int, int, int, int] | None:
        source = self.controller.source_state()
        value = source.attributes.get("rgbww_color") if source else None
        return tuple(value) if value is not None else None

    @property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        source = self.controller.source_state()
        value = source.attributes.get("rgbw_color") if source else None
        return tuple(value) if value is not None else None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        source = self.controller.source_state()
        value = source.attributes.get("rgb_color") if source else None
        return tuple(value) if value is not None else None

    @property
    def hs_color(self) -> tuple[float, float] | None:
        source = self.controller.source_state()
        value = source.attributes.get("hs_color") if source else None
        return tuple(value) if value is not None else None

    @property
    def xy_color(self) -> tuple[float, float] | None:
        source = self.controller.source_state()
        value = source.attributes.get("xy_color") if source else None
        return tuple(value) if value is not None else None

    @property
    def color_temp_kelvin(self) -> int | None:
        state = self.controller.source_state()
        if state is None or not self.controller.is_white():
            return None
        return state.attributes.get("color_temp_kelvin")

    @property
    def brightness(self) -> int | None:
        return self.controller.display_brightness()

    @property
    def extra_state_attributes(self) -> dict:
        command = self.controller
        return {
            "requested_illuminance_lx": round(command.target_lux, 2),
            "source_entity_id": command.source,
            "source_color_mode": (
                command.source_state().attributes.get("color_mode")
                if command.source_state()
                else None
            ),
        }

    async def async_turn_on(self, **kwargs) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        transition = kwargs.get(ATTR_TRANSITION)
        raw_controls = (
            ATTR_EFFECT,
            ATTR_FLASH,
            ATTR_HS_COLOR,
            ATTR_RGB_COLOR,
            ATTR_RGBW_COLOR,
            ATTR_RGBWW_COLOR,
            ATTR_XY_COLOR,
            ATTR_WHITE,
        )
        if any(key in kwargs for key in raw_controls) or (
            kelvin is None and self.controller.uses_raw_brightness()
        ):
            await self.controller.forward_raw(kwargs)
        elif brightness is not None:
            await self.controller.set_brightness(brightness, kelvin, transition)
        elif kelvin is not None:
            await self.controller.set_kelvin(kelvin, transition)
        else:
            await self.controller.turn_on(transition)

    async def async_turn_off(self, **kwargs) -> None:
        await self.controller.turn_off(kwargs.get(ATTR_TRANSITION), kwargs.get(ATTR_FLASH))
