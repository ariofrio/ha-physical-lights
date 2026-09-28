"""Melanopic Light integration."""

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, PLATFORMS
from .controller import Controller
from .source import calibrated_source


async def async_setup_entry(hass, entry) -> bool:
    source_entity_id = entry.options.get("source_entity_id", entry.data["source_entity_id"])
    if calibrated_source(hass, source_entity_id) is None:
        raise ConfigEntryNotReady("Selected Calibrated Light is not ready")
    controller = Controller(hass, entry)
    await controller.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller

    @callback
    def source_changed(event) -> None:
        controller.notify()

    entry.async_on_unload(
        async_track_state_change_event(hass, [controller.source_entity_id], source_changed)
    )
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_update_options(hass, entry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
