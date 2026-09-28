"""Shared requested and observed state for one calibrated position."""

from __future__ import annotations

from collections.abc import Callable
from math import isfinite

from homeassistant.components.light import ColorMode
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.storage import Store

from .const import CONF_REFERENCE, CONF_SOURCE, DOMAIN
from .model import A23, brightness_for_lux, map_brightness, plan_target


class Controller:
    """One source bulb and one calibrated receiving position."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.source = entry.options.get(CONF_SOURCE, entry.data[CONF_SOURCE])
        self.model = A23
        self.reference_lux = float(entry.options.get(CONF_REFERENCE, entry.data[CONF_REFERENCE]))
        self.target_lux = self.model.lux(
            self.model.min_dim, self.model.reference_kelvin, self.reference_lux
        )
        self.kelvin = self.model.reference_kelvin
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.listeners: list[Callable[[], None]] = []
        self.pending_adoption = False
        self.last_raw_settings: dict | None = None

    async def async_load(self) -> None:
        data = await self.store.async_load() or {}
        if isinstance(data.get("last_raw_settings"), dict):
            self.last_raw_settings = data["last_raw_settings"]
        target = data.get("target_lux")
        kelvin = data.get("kelvin")
        if (
            isinstance(target, (int, float))
            and not isinstance(target, bool)
            and isfinite(target)
            and target >= 0
            and isinstance(kelvin, int)
            and not isinstance(kelvin, bool)
            and self.model.min_kelvin <= kelvin <= self.model.max_kelvin
        ):
            self.target_lux = float(target)
            self.kelvin = kelvin
            return
        self.pending_adoption = True
        await self.async_finish_adoption()

    async def async_finish_adoption(self) -> None:
        """Adopt the first usable source state when there is no saved request."""
        if not self.pending_adoption:
            return
        state = self.source_state()
        if state is None or state.state in ("unknown", "unavailable"):
            return
        if self.is_white():
            actual_lux = self.estimated_lux()
            if actual_lux is not None and actual_lux > 0:
                self.kelvin = round(state.attributes["color_temp_kelvin"])
                self.target_lux = actual_lux
        self.pending_adoption = False
        await self._save()
        self.notify()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self.listeners.append(listener)

        def remove() -> None:
            self.listeners.remove(listener)

        return remove

    @callback
    def notify(self) -> None:
        for listener in tuple(self.listeners):
            listener()

    def source_state(self) -> State | None:
        return self.hass.states.get(self.source)

    def is_white(self, state: State | None = None) -> bool:
        state = state or self.source_state()
        return (
            state is not None
            and state.attributes.get("color_mode") == ColorMode.COLOR_TEMP
            and state.attributes.get("effect") in (None, "off")
        )

    @staticmethod
    def _raw_settings(state: State) -> dict | None:
        attributes = state.attributes
        settings = {}
        if effect := attributes.get("effect"):
            if effect != "off":
                settings["effect"] = effect
        if not settings:
            color_key = {
                ColorMode.RGB: "rgb_color",
                ColorMode.RGBW: "rgbw_color",
                ColorMode.RGBWW: "rgbww_color",
                ColorMode.HS: "hs_color",
                ColorMode.XY: "xy_color",
            }.get(attributes.get("color_mode"))
            if color_key and (value := attributes.get(color_key)) is not None:
                settings[color_key] = value
        if (brightness := attributes.get("brightness")) is not None:
            if attributes.get("color_mode") == ColorMode.WHITE:
                settings["white"] = brightness
            else:
                settings["brightness"] = brightness
        return settings or None

    def observe_source(self, previous: State | None = None) -> None:
        state = self.source_state()
        if state is None:
            return
        before = self.last_raw_settings
        if state.state == STATE_ON:
            self.last_raw_settings = None if self.is_white(state) else self._raw_settings(state)
        elif previous is not None and previous.state == STATE_ON and not self.is_white(previous):
            self.last_raw_settings = self._raw_settings(previous)
        else:
            return
        if self.last_raw_settings != before and (
            self.last_raw_settings is None or before is None or state.state != STATE_ON
        ):
            self.hass.async_create_task(self._save())

    def uses_raw_brightness(self) -> bool:
        state = self.source_state()
        if state is not None and state.state == STATE_ON:
            return not self.is_white(state)
        return self.last_raw_settings is not None

    def estimated_lux(self) -> float | None:
        state = self.source_state()
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        if state.state != STATE_ON:
            return 0.0
        if not self.is_white():
            return None
        brightness = state.attributes.get("brightness")
        kelvin = state.attributes.get("color_temp_kelvin")
        if not isinstance(brightness, (int, float)) or not isinstance(kelvin, (int, float)):
            return None
        dim = max(self.model.min_dim, min(self.model.max_dim, round(brightness * 100 / 255)))
        try:
            return self.model.lux(dim, round(kelvin), self.reference_lux)
        except ValueError:
            return None

    def display_brightness(self) -> int | None:
        state = self.source_state()
        if state is None or state.state != STATE_ON:
            return None
        actual = self.estimated_lux()
        if actual is None:
            return state.attributes.get("brightness")
        if actual == 0:
            return None
        return brightness_for_lux(
            self.model, actual, round(state.attributes["color_temp_kelvin"]), self.reference_lux
        )

    async def set_target(self, target: float) -> None:
        if not isfinite(target) or target < 0:
            raise ValueError("Target illuminance must be nonnegative and finite")
        self.target_lux = float(target)
        self.last_raw_settings = None
        await self._save()
        await self.apply()

    async def set_target_and_kelvin(
        self, target: float, kelvin: int, transition: float | None = None
    ) -> None:
        """Apply one requested lux/CCT pair in a single source-light command."""
        if not isfinite(target) or target < 0:
            raise ValueError("Target illuminance must be nonnegative and finite")
        if not self.model.min_kelvin <= kelvin <= self.model.max_kelvin:
            raise ValueError("CCT outside measured range")
        self.target_lux = float(target)
        self.kelvin = kelvin
        self.last_raw_settings = None
        await self._save()
        await self.apply(transition)

    async def set_brightness(
        self, brightness: int, kelvin: int | None = None, transition: float | None = None
    ) -> None:
        if kelvin is not None:
            self.kelvin = kelvin
        self.target_lux = map_brightness(self.model, brightness, self.kelvin, self.reference_lux)
        self.last_raw_settings = None
        await self._save()
        await self.apply(transition)

    async def set_kelvin(self, kelvin: int, transition: float | None = None) -> None:
        if not self.model.min_kelvin <= kelvin <= self.model.max_kelvin:
            raise ValueError("CCT outside measured range")
        self.kelvin = kelvin
        self.last_raw_settings = None
        await self._save()
        await self.apply(transition)

    async def turn_on(self, transition: float | None = None) -> None:
        if self.last_raw_settings is not None and self.uses_raw_brightness():
            attributes = {"transition": transition} if transition is not None else {}
            await self.forward_raw(attributes)
            return
        if self.pending_adoption:
            await self._save()
        if self.target_lux == 0:
            self.target_lux = self.model.lux(self.model.min_dim, self.kelvin, self.reference_lux)
            await self._save()
        await self.apply(transition)

    async def turn_off(self, transition: float | None = None, flash: str | None = None) -> None:
        if self.pending_adoption:
            await self._save()
        state = self.source_state()
        if state is not None and state.state == STATE_ON and not self.is_white(state):
            self.last_raw_settings = self._raw_settings(state)
            await self._save()
        data = {"entity_id": self.source}
        if transition is not None:
            data["transition"] = transition
        if flash is not None:
            data["flash"] = flash
        await self.hass.services.async_call("light", "turn_off", data, blocking=True)
        self.notify()

    async def forward_raw(self, attributes: dict) -> None:
        state = self.source_state()
        if state is None or state.state != STATE_ON:
            if self.last_raw_settings is not None and not any(
                key in attributes
                for key in (
                    "effect",
                    "rgb_color",
                    "rgbw_color",
                    "rgbww_color",
                    "hs_color",
                    "xy_color",
                    "white",
                )
            ):
                attributes = {**self.last_raw_settings, **attributes}
                if "white" in self.last_raw_settings and "brightness" in attributes:
                    attributes["white"] = attributes.pop("brightness")
        await self.hass.services.async_call(
            "light", "turn_on", {"entity_id": self.source, **attributes}, blocking=True
        )
        self.notify()

    async def apply(self, transition: float | None = None) -> None:
        command = plan_target(self.model, self.target_lux, self.kelvin, self.reference_lux)
        self.notify()
        if command.dim is None:
            await self.turn_off(transition)
            return
        data = {
            "entity_id": self.source,
            "brightness": command.ha_brightness,
            "color_temp_kelvin": self.kelvin,
        }
        if transition is not None:
            data["transition"] = transition
        await self.hass.services.async_call(
            "light",
            "turn_on",
            data,
            blocking=True,
        )
        self.notify()

    async def set_reference(self, reference_lux: float) -> None:
        if not isfinite(reference_lux) or reference_lux <= 0:
            raise ValueError("Reference illuminance must be positive and finite")
        self.reference_lux = float(reference_lux)
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_REFERENCE: reference_lux}
        )
        self.notify()

    async def _save(self) -> None:
        self.pending_adoption = False
        await self.store.async_save(
            {
                "target_lux": self.target_lux,
                "kelvin": self.kelvin,
                "last_raw_settings": self.last_raw_settings,
            }
        )
