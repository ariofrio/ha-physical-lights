"""Select a measured bulb model and receiving-position calibration."""

import math

import voluptuous as vol
from homeassistant.config_entries import OptionsFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import CONF_MODEL, CONF_NAME, CONF_REFERENCE, CONF_SOURCE, DOMAIN
from .model import A23


def _schema(defaults=None):
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Calibrated light")): vol.All(
                str, vol.Length(min=1, max=64)
            ),
            vol.Required(
                CONF_SOURCE, default=defaults.get(CONF_SOURCE, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="light")),
            vol.Required(
                CONF_MODEL, default=defaults.get(CONF_MODEL, A23.model_id)
            ): SelectSelector(
                SelectSelectorConfig(options=[{"value": A23.model_id, "label": A23.name}])
            ),
            vol.Required(CONF_REFERENCE, default=defaults.get(CONF_REFERENCE, 173)): NumberSelector(
                NumberSelectorConfig(min=0.1, max=100000, step=0.1, mode=NumberSelectorMode.BOX)
            ),
        }
    )


def _options_schema(defaults):
    return vol.Schema(
        {
            vol.Required(CONF_SOURCE, default=defaults[CONF_SOURCE]): EntitySelector(
                EntitySelectorConfig(domain="light")
            ),
            vol.Required(CONF_MODEL, default=defaults[CONF_MODEL]): SelectSelector(
                SelectSelectorConfig(options=[{"value": A23.model_id, "label": A23.name}])
            ),
            vol.Required(CONF_REFERENCE, default=defaults[CONF_REFERENCE]): NumberSelector(
                NumberSelectorConfig(min=0.1, max=100000, step=0.1, mode=NumberSelectorMode.BOX)
            ),
        }
    )


def _errors(hass, data, current_entry_id=None):
    if data[CONF_MODEL] != A23.model_id:
        return {CONF_MODEL: "unsupported_model"}
    state = hass.states.get(data[CONF_SOURCE])
    if state is None:
        return {CONF_SOURCE: "source_missing"}
    registry_entry = er.async_get(hass).async_get(data[CONF_SOURCE])
    if registry_entry is not None and registry_entry.platform == DOMAIN:
        return {CONF_SOURCE: "proxy_as_source"}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (
            entry.data.get("kind") == "calibrated"
            and entry.entry_id != current_entry_id
            and (entry.options.get(CONF_SOURCE, entry.data[CONF_SOURCE]) == data[CONF_SOURCE])
        ):
            return {CONF_SOURCE: "source_already_configured"}
    modes = state.attributes.get("supported_color_modes", [])
    if "color_temp" not in modes:
        return {CONF_SOURCE: "source_not_tunable_white"}
    if not math.isfinite(data[CONF_REFERENCE]) or data[CONF_REFERENCE] <= 0:
        return {CONF_REFERENCE: "invalid_reference"}
    return {}


class CalibratedLightOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = _errors(
                self.hass, {**self.config_entry.data, **user_input}, self.config_entry.entry_id
            )
            if not errors:
                return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                user_input or {**self.config_entry.data, **self.config_entry.options}
            ),
            errors=errors,
        )
