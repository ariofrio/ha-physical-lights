"""Common entity metadata and source-subscription behavior."""

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


class MelanopicEntity:
    _attr_has_entity_name = True

    def __init__(self, controller, suffix: str) -> None:
        self.controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name=controller.entry.title,
            manufacturer="Physical Lights",
            model="Calibrated-light exposure proxy",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.subscribe(self.async_write_ha_state))
