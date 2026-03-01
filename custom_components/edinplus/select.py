"""Select platform for the eDIN+ HomeAssistant integration."""
from __future__ import annotations

import logging

from .edinplus import edinplus_dmx_channel_instance
from .const import DOMAIN, DEFAULT_COLOUR_PALETTE_NAMES

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

LOGGER = logging.getLogger(__name__)

# This function is called as part of the __init__.async_setup_entry
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add selectors for DMX lights with RGB or TW control."""
    npu = hass.data[DOMAIN][config_entry.entry_id]

    # Add selector entities for DMX lights with RGB or TW support
    entities = []
    for light in npu.lights:
        if isinstance(light, edinplus_dmx_channel_instance):
            if light.dmx_type == "dmxrgbcolr":
                entities.append(EdinPlusDMXRGBPresetSelector(light))
            elif light.dmx_type == "dmxtwcolr":
                entities.append(EdinPlusDMXTWPresetSelector(light))
    
    async_add_entities(entities)


class EdinPlusDMXRGBPresetSelector(SelectEntity):
    """Representation of an eDIN+ DMX RGB Preset Selector."""

    should_poll = False

    def __init__(self, light: edinplus_dmx_channel_instance) -> None:
        """Initialise an eDIN+ DMX RGB Preset Selector."""
        self._light = light
        self._attr_name = f"{self._light.name} Preset"
        self._attr_unique_id = f"{self._light.light_id}_rgb_preset"
        
        # Build options list - exclude Tunable White presets (48-55)
        self._attr_options = []
        for preset_num, preset_name in DEFAULT_COLOUR_PALETTE_NAMES.items():
            if preset_num not in range(48, 56):  # Exclude TW presets
                if preset_num < 64: # Temporarily exclude sequences
                    self._attr_options.append(preset_name)
        
        LOGGER.debug(
            f"[{self._light.hub._hostname}] Initialising DMX RGB preset selector: "
            f"{self._attr_name} ({self._attr_unique_id})"
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._light.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._light.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info - same device as the light."""
        suggested_area = self._light.area if self._light.hub._config.auto_suggest_areas else None
        return DeviceInfo(
            identifiers={(DOMAIN, self._light.light_id)},
            name=self._light.name,
            model=self._light.model,
            manufacturer=self._light.hub.manufacturer,
            suggested_area=suggested_area,
            via_device=(DOMAIN, self._light.hub._id),
            configuration_url=f"http://{self._light.hub._hostname}",
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected preset."""
        preset_num = self._light._preset
        if preset_num in DEFAULT_COLOUR_PALETTE_NAMES:
            return DEFAULT_COLOUR_PALETTE_NAMES[preset_num]
        return DEFAULT_COLOUR_PALETTE_NAMES[0]  # "Custom"

    async def async_select_option(self, option: str) -> None:
        """Change the selected preset."""
        # Find preset number by name
        preset_num = None
        for num, name in DEFAULT_COLOUR_PALETTE_NAMES.items():
            if name == option:
                preset_num = num
                break
        
        if preset_num is not None and preset_num not in range(48, 56):
            await self._light.set_preset(preset_num)
            LOGGER.debug(
                f"[{self._light.hub._hostname}] DMX RGB preset changed to {option} ({preset_num})"
            )
        else:
            LOGGER.warning(
                f"[{self._light.hub._hostname}] Invalid RGB preset selected: {option}"
            )


class EdinPlusDMXTWPresetSelector(SelectEntity):
    """Representation of an eDIN+ DMX Tunable White Preset Selector."""

    should_poll = False

    def __init__(self, light: edinplus_dmx_channel_instance) -> None:
        """Initialise an eDIN+ DMX TW Preset Selector."""
        self._light = light
        self._attr_name = f"{self._light.name} Preset"
        self._attr_unique_id = f"{self._light.light_id}_tw_preset"
        
        # Build options list - only include Tunable White presets (48-55) and Custom (0)
        self._attr_options = []
        for preset_num, preset_name in DEFAULT_COLOUR_PALETTE_NAMES.items():
            if preset_num == 0 or preset_num in range(48, 56):  # Include Custom and TW presets
                self._attr_options.append(preset_name)
        
        LOGGER.debug(
            f"[{self._light.hub._hostname}] Initialising DMX TW preset selector: "
            f"{self._attr_name} ({self._attr_unique_id})"
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._light.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._light.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info - same device as the light."""
        suggested_area = self._light.area if self._light.hub._config.auto_suggest_areas else None
        return DeviceInfo(
            identifiers={(DOMAIN, self._light.light_id)},
            name=self._light.name,
            model=self._light.model,
            manufacturer=self._light.hub.manufacturer,
            suggested_area=suggested_area,
            via_device=(DOMAIN, self._light.hub._id),
            configuration_url=f"http://{self._light.hub._hostname}",
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected preset."""
        preset_num = self._light._preset
        if preset_num in DEFAULT_COLOUR_PALETTE_NAMES:
            return DEFAULT_COLOUR_PALETTE_NAMES[preset_num]
        return DEFAULT_COLOUR_PALETTE_NAMES[0]  # "Custom"

    async def async_select_option(self, option: str) -> None:
        """Change the selected preset."""
        # Find preset number by name
        preset_num = None
        for num, name in DEFAULT_COLOUR_PALETTE_NAMES.items():
            if name == option:
                preset_num = num
                break
        
        if preset_num is not None and (preset_num == 0 or preset_num in range(48, 56)):
            await self._light.set_preset(preset_num)
            LOGGER.debug(
                f"[{self._light.hub._hostname}] DMX TW preset changed to {option} ({preset_num})"
            )
        else:
            LOGGER.warning(
                f"[{self._light.hub._hostname}] Invalid TW preset selected: {option}"
            )
