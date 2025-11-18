"""Button platform for the eDIN+ HomeAssistant integration."""
from __future__ import annotations

from typing import Any

import logging
from .const import DOMAIN

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

LOGGER = logging.getLogger(__name__)

# This function is called as part of the __init__.async_setup_entry (via the
# hass.config_entries.async_forward_entry_setup call)
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add buttons for passed config_entry in HA."""
    # The hub is loaded from the associated hass.data entry that was created in the
    # __init__.async_setup_entry function
    npu = hass.data[DOMAIN][config_entry.entry_id]

    # Add all entities to HA; these are low-level button objects from the
    # TCP client module, but this wrapper only relies on their public API.
    async_add_entities(
        EdinPlusRelayPulseButton(button) for button in npu.buttons
    )

class EdinPlusRelayPulseButton(ButtonEntity):
    """Representation of an eDIN+ Relay Pulse Button."""

    def __init__(self, button) -> None:
        """Initialise an eDIN+ Relay Button."""
        self._button = button
        self._attr_name = self._button.name
        self._attr_unique_id = f"{self._button.button_id}_button"
        self._state = None
        LOGGER.debug(f"[{self._button.hub._hostname}] Initialising button: {self._button.name} ({self._button.button_id})")

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The device has a register_callback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called wherever there are changes.
        # The callback registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._button.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered callbacks here.
        self._button.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info"""
        return DeviceInfo(
            identifiers={(DOMAIN,self._button.button_id)},
            name=self.name,
            sw_version="1.0.0",
            model=self._button.model,
            manufacturer=self._button.hub.manufacturer,
            suggested_area=self._button.area,
            via_device=(DOMAIN,self._button.hub._id),
            configuration_url=f"http://{self._button.hub._hostname}",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self._button.press()