"""Choose and configure a Physical Lights device."""

from uuid import uuid4

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow

from . import KIND_CALIBRATED, KIND_DAYLIGHT, KIND_MELANOPIC
from .calibrated.config_flow import CalibratedLightOptionsFlow
from .calibrated.config_flow import _errors as calibrated_errors
from .calibrated.config_flow import _schema as calibrated_schema
from .daylight.config_flow import DaylightOptionsFlow
from .melanopic.config_flow import MelanopicLightOptionsFlow
from .melanopic.config_flow import _errors as melanopic_errors
from .melanopic.config_flow import _schema as melanopic_schema

DOMAIN = "physical_lights"


class PhysicalLightsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return {
            KIND_DAYLIGHT: DaylightOptionsFlow,
            KIND_CALIBRATED: CalibratedLightOptionsFlow,
            KIND_MELANOPIC: MelanopicLightOptionsFlow,
        }[config_entry.data["kind"]]()

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(
            step_id="user",
            menu_options=[KIND_DAYLIGHT, KIND_CALIBRATED, KIND_MELANOPIC],
        )

    async def async_step_daylight(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(uuid4().hex)
            return self.async_create_entry(title=user_input["name"], data={"kind": KIND_DAYLIGHT})
        return self.async_show_form(
            step_id=KIND_DAYLIGHT,
            data_schema=vol.Schema(
                {vol.Required("name", default="Daylight"): vol.All(str, vol.Length(min=1, max=64))}
            ),
        )

    async def async_step_calibrated(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = calibrated_errors(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(uuid4().hex)
                return self.async_create_entry(
                    title=user_input["name"], data={"kind": KIND_CALIBRATED, **user_input}
                )
        return self.async_show_form(
            step_id=KIND_CALIBRATED,
            data_schema=calibrated_schema(user_input),
            errors=errors,
        )

    async def async_step_melanopic(self, user_input=None):
        errors = {}
        if user_input is not None:
            errors = melanopic_errors(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(uuid4().hex)
                return self.async_create_entry(
                    title=user_input["name"], data={"kind": KIND_MELANOPIC, **user_input}
                )
        return self.async_show_form(
            step_id=KIND_MELANOPIC,
            data_schema=melanopic_schema(user_input),
            errors=errors,
        )
