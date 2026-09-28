"""Select a configured Calibrated Light as the melanopic proxy's source."""

import voluptuous as vol
from homeassistant.config_entries import OptionsFlow
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import CONF_NAME, CONF_SOURCE, DOMAIN
from .source import calibrated_source


def _schema(defaults=None):
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Melanopic Light")): vol.All(
                str, vol.Length(min=1, max=64)
            ),
            vol.Required(CONF_SOURCE, default=defaults.get(CONF_SOURCE, vol.UNDEFINED)): (
                EntitySelector(EntitySelectorConfig(domain="light"))
            ),
        }
    )


def _errors(hass, data, current_entry_id=None):
    entity = er.async_get(hass).async_get(data[CONF_SOURCE])
    if entity is None or entity.platform != DOMAIN:
        return {CONF_SOURCE: "not_calibrated_light"}
    if calibrated_source(hass, data[CONF_SOURCE]) is None:
        return {CONF_SOURCE: "source_not_ready"}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (
            entry.data.get("kind") == "melanopic"
            and entry.entry_id != current_entry_id
            and (entry.options.get(CONF_SOURCE, entry.data[CONF_SOURCE]) == data[CONF_SOURCE])
        ):
            return {CONF_SOURCE: "source_already_configured"}
    return {}


class MelanopicLightOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        defaults = {**entry.data, **entry.options}
        errors = {}
        if user_input is not None:
            candidate = {**defaults, **user_input}
            errors = _errors(self.hass, candidate, entry.entry_id)
            if not errors:
                return self.async_create_entry(data={CONF_SOURCE: candidate[CONF_SOURCE]})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SOURCE, default=defaults[CONF_SOURCE]): EntitySelector(
                        EntitySelectorConfig(domain="light")
                    )
                }
            ),
            errors=errors,
        )
