"""Sensor platform for the eDIN+ HomeAssistant integration.

Provides a timestamp sensor indicating when the last message was
received from the NPU. This is associated with a dedicated NPU
status device in the device registry.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up eDIN+ sensors for a config entry."""
    npu = hass.data[DOMAIN][config_entry.entry_id]

    # Sensors attached to the NPU status device
    async_add_entities(
        [
            EdinPlusLastMessageSensor(npu),
            EdinPlusOnlineSensor(npu),
            EdinPlusCommsRetrySensor(npu),
            EdinPlusReconnectDelaySensor(npu),
            EdinPlusReconnectAttemptsSensor(npu),
        ]
    )


class EdinPlusLastMessageSensor(SensorEntity):
    """Sensor showing the timestamp of the last NPU message."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True

    def __init__(self, npu) -> None:
        self._npu = npu
        self._attr_unique_id = f"{self._npu._id}_last_message"
        self._attr_translation_key = "last_npu_message"
        LOGGER.debug("[%s] Initialising last NPU message sensor", self._npu._hostname)

    async def async_added_to_hass(self) -> None:
        """Ensure state is written promptly when we already have data."""
        if self._npu.last_message_received is not None:
            self.async_write_ha_state()
            
    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last message from the NPU."""
        return self._npu.last_message_received

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the virtual NPU status device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._npu._id)},
            name=f"NPU {self._npu._hostname}",
            sw_version=self._npu.tcp_version,
            manufacturer=self._npu.manufacturer,
            model=self._npu.model,
            serial_number=self._npu.serial_num,
            configuration_url=f"http://{self._npu._hostname}",
        )


class EdinPlusOnlineSensor(SensorEntity):
    """Diagnostic sensor exposing whether the NPU is online."""

    _attr_has_entity_name = True

    def __init__(self, npu) -> None:
        self._npu = npu
        self._attr_unique_id = f"{self._npu._id}_online"
        self._attr_translation_key = "npu_online"
        LOGGER.debug("[%s] Initialising NPU online sensor", self._npu._hostname)

    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        return "online" if self._npu.online else "offline"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._npu._id)},
            name=f"NPU {self._npu._hostname}",
            sw_version=self._npu.tcp_version,
            manufacturer=self._npu.manufacturer,
            model=self._npu.model,
            serial_number=self._npu.serial_num,
            configuration_url=f"http://{self._npu._hostname}",
        )


class EdinPlusCommsRetrySensor(SensorEntity):
    """Diagnostic sensor exposing current consecutive comms retry attempts."""

    _attr_has_entity_name = True

    def __init__(self, npu) -> None:
        self._npu = npu
        self._attr_unique_id = f"{self._npu._id}_comms_retries"
        self._attr_translation_key = "npu_comms_retries"
        LOGGER.debug("[%s] Initialising NPU comms retry sensor", self._npu._hostname)

    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        return int(self._npu.comms_retry_attempts)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._npu._id)},
            name=f"NPU {self._npu._hostname}",
            sw_version=self._npu.tcp_version,
            manufacturer=self._npu.manufacturer,
            model=self._npu.model,
            serial_number=self._npu.serial_num,
            configuration_url=f"http://{self._npu._hostname}",
        )


class EdinPlusReconnectDelaySensor(SensorEntity):
    """Diagnostic sensor exposing current reconnect backoff delay in seconds."""

    _attr_has_entity_name = True

    def __init__(self, npu) -> None:
        self._npu = npu
        self._attr_unique_id = f"{self._npu._id}_reconnect_delay"
        self._attr_translation_key = "npu_reconnect_delay"
        LOGGER.debug("[%s] Initialising NPU reconnect delay sensor", self._npu._hostname)
        
    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> float:
        return float(self._npu._reconnect_delay)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._npu._id)},
            name=f"NPU {self._npu._hostname}",
            sw_version=self._npu.tcp_version,
            manufacturer=self._npu.manufacturer,
            model=self._npu.model,
            serial_number=self._npu.serial_num,
            configuration_url=f"http://{self._npu._hostname}",
        )


class EdinPlusReconnectAttemptsSensor(SensorEntity):
    """Diagnostic sensor exposing number of consecutive TCP reconnection attempts."""

    _attr_has_entity_name = True

    def __init__(self, npu) -> None:
        self._npu = npu
        self._attr_unique_id = f"{self._npu._id}_reconnect_attempts"
        self._attr_translation_key = "npu_reconnect_attempts"
        LOGGER.debug("[%s] Initialising NPU reconnect attempts sensor", self._npu._hostname)
        
    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        return int(self._npu.reconnect_attempts)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._npu._id)},
            name=f"NPU {self._npu._hostname}",
            sw_version=self._npu.tcp_version,
            manufacturer=self._npu.manufacturer,
            model=self._npu.model,
            serial_number=self._npu.serial_num,
            configuration_url=f"http://{self._npu._hostname}",
        )
