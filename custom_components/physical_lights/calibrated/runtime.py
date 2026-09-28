"""Calibrated white-light proxy."""

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, PLATFORMS
from .controller import Controller


async def async_setup_entry(hass: HomeAssistant, entry) -> bool:
    controller = Controller(hass, entry)
    await controller.async_load()
    controller.observe_source()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller

    @callback
    def source_changed(event) -> None:
        if controller.pending_adoption:
            hass.async_create_task(controller.async_finish_adoption())
        controller.observe_source(event.data.get("old_state"))
        controller.notify()

    entry.async_on_unload(async_track_state_change_event(hass, [controller.source], source_changed))
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_update_options(hass: HomeAssistant, entry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
