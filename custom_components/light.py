"""Platform for light integration."""
from __future__ import annotations

import logging
import requests

from .edinplus import EdinPlusLightChannelInstance,EdinPlusDiscoverChannels
import voluptuous as vol

from pprint import pformat

# Import the device class from the component that you want to support
import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (SUPPORT_BRIGHTNESS, ATTR_BRIGHTNESS,
                                            PLATFORM_SCHEMA, LightEntity)
from homeassistant.const import CONF_NAME, CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

_LOGGER = logging.getLogger("edinplus")

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Required(CONF_IP_ADDRESS): cv.string,
})


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the eDIN+ Light platform."""
    # Add devices
    _LOGGER.info(pformat(config))

    channels = await EdinPlusDiscoverChannels(config[CONF_IP_ADDRESS])

    for channel in channels:
        add_entities([EdinPlusLightChannel(channel)])

class EdinPlusLightChannel(LightEntity):
    """Representation of an Edin Light Channel."""

    def __init__(self, light) -> None:
        """Initialize an eDIN+ Light Channel."""
        _LOGGER.info(pformat(light))
        self._light = EdinPlusLightChannelInstance(light["hostname"],light["address"],light["channel"])
        self._name = light["name"]
        self._unique_id = "edinpluscustomuuid-"+str(light["address"])+"-"+str(light["channel"])
        self._state = None
        self._brightness = None

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique identifier for this light."""
        return self._unique_id

    @property
    def brightness(self):
        """Return the brightness of the light.

        This method is optional. Removing it indicates to Home Assistant
        that brightness is not supported for this light.
        """
        return self._brightness

    @property
    def supported_features(self):
        return SUPPORT_BRIGHTNESS

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._state

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the light to turn on."""
        _LOGGER.debug("Attempting light turn on")
        
        if ATTR_BRIGHTNESS in kwargs:
            await self._light.set_brightness(kwargs.get(ATTR_BRIGHTNESS, 255))

        else:
            await self._light.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""
        await self._light.turn_off()

    def update(self) -> None:
        """Fetch new state data for this light.

        This is the only method that should fetch new data for Home Assistant.
        """
        self._state = self._light.is_on
        self._brightness = self._light.brightness