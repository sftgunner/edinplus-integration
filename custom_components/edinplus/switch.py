"""Switch platform for the eDIN+ HomeAssistant integration."""
from __future__ import annotations

from typing import Any

import logging
from .const import DOMAIN

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.switch import SwitchEntity
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
    """Add switches for passed config_entry in HA."""
    # The hub is loaded from the associated hass.data entry that was created in the
    # __init__.async_setup_entry function
    npu = hass.data[DOMAIN][config_entry.entry_id]

    # Add all entities to HA; these are low-level relay channel objects but we
    # treat them via the switch wrapper class only.
    async_add_entities(
        EdinPlusSwitchChannel(switch) for switch in npu.switches
    )

class EdinPlusSwitchChannel(SwitchEntity):
    """Representation of an eDIN+ Switch Channel."""

    def __init__(self, switch) -> None:
        """Initialise an eDIN+ Switch Channel."""
        self._switch = switch
        self._attr_name = self._switch.name
        self._attr_unique_id = f"{self._switch.switch_id}_switch"
        self._state = None
        LOGGER.debug(f"[{self._switch.hub._hostname}] Initialising switch: {self._switch.name} ({self._switch.switch_id})")

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The device has a register_callback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called wherever there are changes.
        # The callback registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._switch.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered callbacks here.
        self._switch.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info"""
        # Only return a suggested area if auto_suggest_areas is enabled
        suggested_area = self._switch.area if self._switch.hub._config.auto_suggest_areas else None
        return DeviceInfo(
            identifiers={(DOMAIN,self._switch.switch_id)},
            name=self.name,
            sw_version="1.0.0",
            model=self._switch.model,
            manufacturer=self._switch.hub.manufacturer,
            suggested_area=suggested_area,
            via_device=(DOMAIN,self._switch.hub._id),
            configuration_url=f"http://{self._switch.hub._hostname}",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        return self._switch._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Instruct the switch to turn on."""
        await self._switch.turn_on()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the switch to turn off."""
        await self._switch.turn_off()