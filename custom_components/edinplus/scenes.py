"""Support for eDIN+ scenes in HomeAssistant."""

from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up eDIN+ scene entities."""
    npu = hass.data[DOMAIN][config_entry.entry_id]
    
    # Add scene entities for each discovered scene
    scene_entities = []
    for scene in npu.scenes:
        scene_entities.append(EdinplusScene(scene))
    
    if scene_entities:
        async_add_entities(scene_entities)


class EdinplusScene(Scene):
    """Representation of an eDIN+ scene."""

    def __init__(self, scene) -> None:
        """Initialize the scene."""
        self._scene = scene
        self._attr_name = scene.name
        self._attr_unique_id = scene.scene_num
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, scene.scene_num)},
            name=scene.name,
            manufacturer=scene.hub.manufacturer,
            model="eDIN+ Scene",
            via_device=(DOMAIN, scene.hub._id),
        )

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate the scene."""
        await self._scene.activate()


class edinplus_scene_instance:
    """Class representing an eDIN+ scene."""
    
    def __init__(self, scene_num: int, scene_name: str, scene_area: str, npu) -> None:
        """Initialize the scene instance."""
        self.scene_num = f"edinplus-{npu.serial}-scene-{scene_num}"
        self._scene_number = scene_num
        self.name = scene_name
        self.area = scene_area
        self.hub = npu
        self._callbacks = set()

    async def activate(self):
        """Activate the scene."""
        await self.hub.tcp_send_message(
            self.hub.writer, 
            f"$SCNRECALL,{self._scene_number};"
        )

    def register_callback(self, callback) -> None:
        """Register callback, called when Scene changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback) 