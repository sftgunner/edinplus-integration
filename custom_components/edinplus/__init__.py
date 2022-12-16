"""The Edin Plus integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import logging
LOGGER = logging.getLogger("edinplus")

from . import edinplus

# List of platforms to support. There should be a matching .py file for each,
# eg <light.py> and <sensor.py>
PLATFORMS: list[str] = ["light"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NPU from config entry."""
    # Store an instance of the "connecting" class that does the work of speaking
    # with your actual devices.
    hub = edinplus.edinplus_NPU_instance(hass, entry.data["host"])
    LOGGER.debug("Initialised NPU instance")

    hass.data.setdefault("edinplus", {})[entry.entry_id] = hub


    # Initialise the TCP connection to the hub
    await hub.async_tcp_connect()
    LOGGER.debug("Completed TCP connect")
    # Ensure that all the devices are up to date on initialisation
    await hub.discover()
    LOGGER.debug("Completed discover")
    # Monitor the TCP connection for any changes
    await hub.monitor(hass)
    LOGGER.debug("Completed monitor")

    # This creates each HA object for each platform your device requires.
    # It's done by calling the `async_setup_entry` function in each platform module.
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    LOGGER.debug("Completed platform setup")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when an entry/configured device is to be removed. The class
    # needs to unload itself, and remove callbacks. See the classes for further
    # details
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data["edinplus"].pop(entry.entry_id)

    return unload_ok