"""Switch platform for the eDIN+ HomeAssistant integration."""
from __future__ import annotations

from typing import Any

import logging
import requests

from .edinplus import edinplus_input_binary_sensor_instance
from .const import DOMAIN
import voluptuous as vol

from pprint import pformat

# Import the device class from the component that you want to support
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.binary_sensor import (PLATFORM_SCHEMA, BinarySensorEntity)
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
    """Add cover for passed config_entry in HA."""
    # The hub is loaded from the associated hass.data entry that was created in the
    # __init__.async_setup_entry function
    npu = hass.data[DOMAIN][config_entry.entry_id]

    # Add all entities to HA
    async_add_entities(EdinPlusBinarySensor(binary_sensor) for binary_sensor in npu.binary_sensors)

class EdinPlusBinarySensor(BinarySensorEntity):
    """Representation of an eDIN+ Binary Sensor."""

    # should_poll = False

    def __init__(self, binary_sensor) -> None:
        """Initialise an eDIN+ Switch Channel."""
        LOGGER.info("Initialising binary sensor for input channel")
        # LOGGER.info(pformat(light))
        self._binary_sensor = binary_sensor
        self._attr_name = self._binary_sensor.name
        self._attr_unique_id = f"{self._binary_sensor.sensor_id}_binary_sensor"
        self._state = None

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._binary_sensor.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._binary_sensor.remove_callback(self.async_write_ha_state)

    @property
    def device_info(self) -> DeviceInfo:
        """Match sensor to the input device"""
        return DeviceInfo(
            identifiers={(DOMAIN,self._binary_sensor.sensor_id)},
            name=self.name,
            sw_version="1.0.0",
            model=self._binary_sensor.model,
            manufacturer=self._binary_sensor.hub.manufacturer,
            suggested_area=self._binary_sensor.area,
            via_device=(DOMAIN,self._binary_sensor.hub._id),
            configuration_url=f"http://{self._binary_sensor.hub._hostname}",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if sensor is closed."""
        return self._binary_sensor._is_on

# Can also add device_class... possibly as opening?