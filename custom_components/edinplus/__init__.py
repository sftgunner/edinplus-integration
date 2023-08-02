"""The eDin+ (by Mode Lighting) HomeAssistant integration"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import logging
# Import constants
from .const import DOMAIN

LOGGER = logging.getLogger(__name__)

from . import edinplus

# List of platforms to support. There should be a matching .py file for each,
# eg <light.py> and <sensor.py>
PLATFORMS: list[str] = ["light","switch","button"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NPU from config entry."""
    # This stores an instance of the NPU class that communicates with other devices
    hub = edinplus.edinplus_NPU_instance(hass, entry.data["host"], entry.entry_id)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    
    LOGGER.debug("Initialised NPU instance")

    # Initialise the TCP connection to the hub
    # In future this could be done after completing the discover step, so that only only one concurrent connection is made from HA to the NPU at a time
    await hub.async_tcp_connect()
    LOGGER.debug("Completed TCP connect")
    
    # Ensure that all the devices are up to date on initialisation (i.e. scan for all connected devices)
    await hub.discover(entry)
    LOGGER.debug("Completed discover")
    
    # Monitor the TCP connection for any changes
    await hub.monitor(hass)
    LOGGER.debug("Completed monitor")

    # This creates each HA object for each platform your device requires (e.g. light, switch)
    # It's done by calling the `async_setup_entry` function in each platform module.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    LOGGER.debug("Completed platform setup")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    # This has just been left as in the example repo - to be further investigated/improved
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok