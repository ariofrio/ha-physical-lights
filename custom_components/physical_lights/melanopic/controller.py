"""Requested and observed state for one melanopic light proxy."""

from collections.abc import Callable
from math import isfinite

from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import CONF_SOURCE, DEFAULT_DELTA, DOMAIN
from .planner import EdiPlan, plan_edi
from .source import calibrated_source
from .spectral import MAX_KELVIN, MIN_KELVIN, melanopic_der


class Controller:
    """Map one lamp-only EDI request onto one calibrated photopic source."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.source_entity_id = entry.options.get(CONF_SOURCE, entry.data[CONF_SOURCE])
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.preferred_kelvin = 4000
        self.max_delta = DEFAULT_DELTA
        self.target_edi = 0.0
        self.listeners: list[Callable[[], None]] = []
        self._plan_key = None
        self._plan: EdiPlan | None = None

    def source(self):
        return calibrated_source(self.hass, self.source_entity_id)

    async def async_load(self) -> None:
        saved = await self.store.async_load() or {}
        preferred = saved.get("preferred_kelvin")
        delta = saved.get("max_delta")
        target = saved.get("target_edi")
        if (
            isinstance(preferred, int)
            and not isinstance(preferred, bool)
            and MIN_KELVIN <= preferred <= MAX_KELVIN
            and isinstance(delta, int)
            and not isinstance(delta, bool)
            and 0 <= delta <= 3800
            and isinstance(target, (int, float))
            and not isinstance(target, bool)
            and isfinite(target)
            and target >= 0
        ):
            self.preferred_kelvin = preferred
            self.max_delta = delta
            self.target_edi = float(target)
            return
        source = self.source()
        if source is not None:
            actual_kelvin = source.reported_kelvin()
            if actual_kelvin is not None and MIN_KELVIN <= actual_kelvin <= MAX_KELVIN:
                self.preferred_kelvin = actual_kelvin
                actual_lux = source.estimated_lux()
                if actual_lux is not None and actual_lux > 0:
                    self.target_edi = actual_lux * melanopic_der(actual_kelvin)
        if self.target_edi == 0:
            self.target_edi = self.plan().min_edi
        await self._save()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self.listeners.append(listener)

        def remove() -> None:
            self.listeners.remove(listener)

        return remove

    @callback
    def notify(self) -> None:
        for listener in tuple(self.listeners):
            listener()

    def plan(self) -> EdiPlan:
        source = self.source()
        if source is None:
            raise ValueError("Calibrated Light source is unavailable")
        key = (
            self.target_edi,
            self.preferred_kelvin,
            self.max_delta,
            self.source_entity_id,
            source.calibration_key,
        )
        if key != self._plan_key:
            self._plan = plan_edi(source, self.target_edi, self.preferred_kelvin, self.max_delta)
            self._plan_key = key
        return self._plan

    def estimated_edi(self) -> float | None:
        source = self.source()
        if source is None:
            return None
        lux = source.estimated_lux()
        if lux is None or lux == 0:
            return lux
        kelvin = source.reported_kelvin()
        if kelvin is None:
            return None
        try:
            return lux * melanopic_der(kelvin)
        except ValueError:
            return None

    def is_on(self) -> bool:
        state = self.hass.states.get(self.source_entity_id)
        return state is not None and state.state == STATE_ON

    def display_brightness(self) -> int | None:
        if not self.is_on():
            return None
        achieved = self.estimated_edi()
        if achieved is None:
            return None
        plan = self.plan()
        if plan.max_edi <= plan.min_edi:
            return 255
        return round(
            1
            + 254
            * (min(max(achieved, plan.min_edi), plan.max_edi) - plan.min_edi)
            / (plan.max_edi - plan.min_edi)
        )

    async def set_target(self, target: float, transition: float | None = None) -> None:
        if not isfinite(target) or target < 0:
            raise ValueError("Target melanopic EDI must be nonnegative and finite")
        self.target_edi = float(target)
        await self._save()
        await self.apply(transition)

    async def set_brightness(
        self, brightness: int, preferred_kelvin: int | None = None, transition: float | None = None
    ) -> None:
        if not 1 <= brightness <= 255:
            raise ValueError("Brightness must be 1..255")
        if preferred_kelvin is not None:
            self._validate_kelvin(preferred_kelvin)
            self.preferred_kelvin = preferred_kelvin
        envelope = self.plan()
        self.target_edi = envelope.min_edi + (brightness - 1) / 254 * (
            envelope.max_edi - envelope.min_edi
        )
        await self._save()
        await self.apply(transition)

    async def set_preferred(self, kelvin: int, transition: float | None = None) -> None:
        self._validate_kelvin(kelvin)
        self.preferred_kelvin = kelvin
        await self._save()
        await self.apply(transition)

    async def set_max_delta(self, delta: int) -> None:
        if not 0 <= delta <= 3800:
            raise ValueError("Maximum CCT adjustment must be 0..3800 K")
        self.max_delta = delta
        await self._save()
        if self.is_on():
            await self.apply()
        else:
            self.notify()

    async def turn_on(self, transition: float | None = None) -> None:
        if self.target_edi == 0:
            self.target_edi = self.plan().min_edi
            await self._save()
        await self.apply(transition)

    async def turn_off(self, transition: float | None = None) -> None:
        data = {"entity_id": self.source_entity_id}
        if transition is not None:
            data["transition"] = transition
        await self.hass.services.async_call("light", "turn_off", data, blocking=True)
        self.notify()

    async def apply(self, transition: float | None = None) -> None:
        plan = self.plan()
        source = self.source()
        if source is None:
            raise ValueError("Calibrated Light source is unavailable")
        self.notify()
        await source.async_set_output(plan.requested_lux, plan.kelvin, transition)
        self.notify()

    @staticmethod
    def _validate_kelvin(kelvin: int) -> None:
        if not MIN_KELVIN <= kelvin <= MAX_KELVIN:
            raise ValueError("Preferred CCT outside spectral model range")

    async def _save(self) -> None:
        await self.store.async_save(
            {
                "target_edi": self.target_edi,
                "preferred_kelvin": self.preferred_kelvin,
                "max_delta": self.max_delta,
            }
        )
