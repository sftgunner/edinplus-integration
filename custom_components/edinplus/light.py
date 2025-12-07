"""Light platform for the eDIN+ HomeAssistant integration."""
from __future__ import annotations

from typing import Any

import logging

from .edinplus import edinplus_dimmer_channel_instance
from .const import DOMAIN

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.light import (ATTR_BRIGHTNESS, ColorMode, LightEntity)
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
    """Add lights for passed config_entry in HA."""
    # The hub is loaded from the associated hass.data entry that was created in the
    # __init__.async_setup_entry function
    npu = hass.data[DOMAIN][config_entry.entry_id]

    # Add all entities to HA
    async_add_entities(EdinPlusLightChannel(light) for light in npu.lights)

class EdinPlusLightChannel(LightEntity):
    """Representation of an eDIN+ Dimmable Light Channel."""

    should_poll = False

    def __init__(self, light) -> None:
        """Initialise an eDIN+ Light Channel."""
        self._light = light
        self._attr_name = self._light.name
        self._attr_unique_id = f"{self._light.light_id}_light"
        self._state = None
        LOGGER.debug(f"[{self._light.hub._hostname}] Initialising light: {self._light.name} ({self._light.light_id})")

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The device has a register_callback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called wherever there are changes.
        # The callback registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._light.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered callbacks here.
        self._light.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info"""
        # Only return a suggested area if auto_suggest_areas is enabled
        suggested_area = self._light.area if self._light.hub._config.auto_suggest_areas else None
        return DeviceInfo(
            identifiers={(DOMAIN,self._light.light_id)},
            name=self.name,
            model=self._light.model,
            manufacturer=self._light.hub.manufacturer,
            suggested_area=suggested_area,
            via_device=(DOMAIN,self._light.hub._id),
            configuration_url=f"http://{self._light.hub._hostname}",
        )

    @property
    def brightness(self):
        """Return the brightness of the light.

        This method is optional. Removing it indicates to Home Assistant
        that brightness is not supported for this light.
        """
        if self._light._brightness is None:
            return 0
        else:
            return int(self._light._brightness)

    @property
    def supported_color_modes(self):
        return {ColorMode.BRIGHTNESS}

    @property
    def color_mode(self):
        return ColorMode.BRIGHTNESS

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        if self._light._brightness is None:
            return False
        else:
            return (int(self._light._brightness) > 0)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the light to turn on."""
        
        if ATTR_BRIGHTNESS in kwargs:
            await self._light.set_brightness(kwargs.get(ATTR_BRIGHTNESS, 255))
        else:
            await self._light.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""
        await self._light.turn_off()

    async def async_update(self) -> None:
        """Fetch new state data for this light.

        This is the only method that should fetch new data for Home Assistant.
        """
        # This should no longer be used, as this relies on HTTP rather than the TCP stream
        LOGGER.warning(f"[{self._light.hub._hostname}] async HTTP update performed - this action should be updated to use the TCP stream")
        self._brightness = await self._light.get_brightness()
        if int(self._brightness) > 0:
            self._state = True
        else:
            self._state = False