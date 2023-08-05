"""Switch platform for the eDIN+ HomeAssistant integration."""
from __future__ import annotations

from typing import Any

import logging
import requests

from .edinplus import edinplus_relay_channel_instance
from .const import DOMAIN
import voluptuous as vol

from pprint import pformat

# Import the device class from the component that you want to support
# import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.switch import (PLATFORM_SCHEMA, SwitchEntity)
# from homeassistant.const import CONF_NAME, CONF_IP_ADDRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
# from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

LOGGER = logging.getLogger(__name__)

# This function is called as part of the __init__.async_setup_entry (via the
# hass.config_entries.async_forward_entry_setup call)
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add cover for passed config_entry in HA."""
    # The hub is loaded from the associated hass.data entry that was created in the
    # __init__.async_setup_entry function
    npu = hass.data[DOMAIN][config_entry.entry_id]

    # Add all entities to HA
    async_add_entities(EdinPlusSwitchChannel(switch) for switch in npu.switches)

class EdinPlusSwitchChannel(SwitchEntity):
    """Representation of an eDIN+ Switch Channel."""

    # should_poll = False

    def __init__(self, switch) -> None:
        """Initialise an eDIN+ Switch Channel."""
        LOGGER.info("Initialising Switch Channel")
        # LOGGER.info(pformat(light))
        self._switch = switch
        self._attr_name = self._switch.name
        self._attr_unique_id = f"{self._switch.switch_id}_switch"
        self._state = None

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The dummy device has a registercallback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._switch.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._switch.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info"""
        return DeviceInfo(
            identifiers={(DOMAIN,self._switch.switch_id)},
                name=self.name,
                sw_version="1.0.0",
                model=self._switch.model,
                manufacturer=self._switch.hub.manufacturer,
                suggested_area=self._switch.area,
                via_device=(DOMAIN,self._switch.hub._id),
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._switch._is_on
    #     if self._light._brightness == None:
    #         return False
    #     else:
    #         return (int(self._light._brightness) > 0)
    #     # return (int(self._light._brightness) > 0)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the switch to turn on."""
        
        await self._switch.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the switch to turn off."""
        await self._switch.turn_off()

    # async def async_update(self) -> None:
    #     """Fetch new state data for this light.

    #     This is the only method that should fetch new data for Home Assistant.
    #     """
    #     # This should no longer be used, as this relies on HTTP rather than the TCP stream
    #     # LOGGER.warning("async HTTP update performed - this action should be updated to use the TCP stream")
    #     # self._brightness = await self._li.get_brightness()
    #     # if int(self._brightness) > 0:
    #     #     self._state = True
    #     # else:
    #     #     self._state = False
    #     #self._state = self._light.is_on
    #     #self._brightness = self._light.brightness