"""Light platform for the eDIN+ HomeAssistant integration."""
from __future__ import annotations

from typing import Any

import logging

from .edinplus import edinplus_dimmer_channel_instance, edinplus_dmx_channel_instance
from .const import DOMAIN, DEFAULT_COLOUR_PALETTE_NAMES, DEFAULT_COLOUR_PALETTE_VALS

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.light import (
    ATTR_BRIGHTNESS, 
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode, 
    LightEntity
)
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
    entities = []
    for light in npu.lights:
        if isinstance(light, edinplus_dmx_channel_instance):
            entities.append(EdinPlusDMXLightChannel(light))
        else:
            entities.append(EdinPlusLightChannel(light))
    
    async_add_entities(entities)

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


class EdinPlusDMXLightChannel(LightEntity):
    """Representation of an eDIN+ DMX Light Channel with optional RGBW or Tunable White."""

    should_poll = False

    def __init__(self, light: edinplus_dmx_channel_instance) -> None:
        """Initialise an eDIN+ DMX Light Channel."""
        self._light = light
        self._attr_name = self._light.name
        self._attr_unique_id = f"{self._light.light_id}_light"
        self._state = None
        
        # Determine supported color modes based on DMX type
        if self._light.dmx_type == "dmxrgbcolr":
            self._attr_supported_color_modes = {ColorMode.RGBW}
            self._attr_color_mode = ColorMode.RGBW
        elif self._light.dmx_type == "dmxtwcolr":
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_color_mode = ColorMode.COLOR_TEMP
            # Tunable white range from presets (1800K to 7000K)
            self._attr_min_color_temp_kelvin = 1800
            self._attr_max_color_temp_kelvin = 7000
        else:
            # Standard DMX - brightness only
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        
        LOGGER.debug(
            f"[{self._light.hub._hostname}] Initialising DMX light: {self._light.name} "
            f"({self._light.light_id}) type: {self._light.dmx_type}"
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._light.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._light.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info"""
        suggested_area = self._light.area if self._light.hub._config.auto_suggest_areas else None
        return DeviceInfo(
            identifiers={(DOMAIN, self._light.light_id)},
            name=self.name,
            model=self._light.model,
            manufacturer=self._light.hub.manufacturer,
            suggested_area=suggested_area,
            via_device=(DOMAIN, self._light.hub._id),
            configuration_url=f"http://{self._light.hub._hostname}",
        )

    @property
    def brightness(self):
        """Return the brightness of the light."""
        if self._light._brightness is None:
            return 0
        else:
            return int(self._light._brightness)

    @property
    def supported_color_modes(self):
        return self._attr_supported_color_modes

    @property
    def color_mode(self):
        return self._attr_color_mode

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        if self._light._brightness is None:
            return False
        else:
            return (int(self._light._brightness) > 0)
    
    @property
    def rgb_color(self):
        """Return the RGB color value [r, g, b]."""
        if self._light.dmx_type == "dmxrgbcolr" and self._light._rgb_color is not None:
            return self._light._rgb_color
        return None
    
    @property
    def rgbw_color(self):
        """Return the RGBW color value [r, g, b, w]."""
        if self._light.dmx_type == "dmxrgbcolr" and self._light._rgb_color is not None:
            r, g, b = self._light._rgb_color
            w = self._light._white_value if self._light._white_value is not None else 0
            return (r, g, b, w)
        return None
    
    @property
    def color_temp_kelvin(self):
        """Return the color temperature in Kelvin."""
        if self._light.dmx_type == "dmxtwcolr" and self._light._color_temp is not None:
            return self._light._color_temp
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the light to turn on."""
        
        # Handle brightness
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
            await self._light.set_brightness(brightness)
        
        # Handle RGBW color
        if ATTR_RGBW_COLOR in kwargs and self._light.dmx_type == "dmxrgbcolr":
            r, g, b, w = kwargs[ATTR_RGBW_COLOR]
            await self._light.set_rgb_color(r, g, b, w)
        elif ATTR_RGB_COLOR in kwargs and self._light.dmx_type == "dmxrgbcolr":
            r, g, b = kwargs[ATTR_RGB_COLOR]
            await self._light.set_rgb_color(r, g, b, 0)
        
        # Handle color temperature
        if ATTR_COLOR_TEMP_KELVIN in kwargs and self._light.dmx_type == "dmxtwcolr":
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            await self._light.set_color_temp(kelvin)
        
        # If no specific attributes, just turn on
        if not any(k in kwargs for k in [ATTR_BRIGHTNESS, ATTR_RGBW_COLOR, ATTR_RGB_COLOR, ATTR_COLOR_TEMP_KELVIN]):
            await self._light.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""
        await self._light.turn_off()
