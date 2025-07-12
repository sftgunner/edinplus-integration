"""The eDin+ (by Mode Lighting) HomeAssistant integration"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import logging
# Import constants
from .const import DOMAIN

LOGGER = logging.getLogger(__name__)

from . import edinplus

# List of platforms to support. There should be a matching .py file for each,
# eg <light.py> and <sensor.py>
PLATFORMS: list[str] = ["light","switch","button","binary_sensor","scene"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NPU from config entry."""
    # This stores an instance of the NPU class that communicates with other devices
    edinplus_npu = edinplus.edinplus_NPU_instance(hass, entry.data["host"], entry.entry_id)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = edinplus_npu
    
    LOGGER.debug("Initialised NPU instance")
    
    # Initialise the TCP connection to the hub
    await edinplus_npu.async_tcp_connect()
    LOGGER.debug("Completed TCP connect")
    
    # # Add the NPU into the device registry - not required, but it makes things neater, and means the NPU shows up as a device in HA (and also appropriately shows device hierarchy)
    # device_registry = dr.async_get(edinplus_npu._hass)
    # LOGGER.debug(f"[{edinplus_npu._hostname}] Creating device in registry with name NPU ({edinplus_npu._name}) and id {edinplus_npu._id}")
    # device_registry.async_get_or_create(
    #     config_entry_id = entry.entry_id,
    #     identifiers={(DOMAIN, edinplus_npu._id)},
    #     manufacturer=edinplus_npu.manufacturer,
    #     name=f"NPU ({edinplus_npu._name})",
    #     model=edinplus_npu.model,
    #     configuration_url=f"http://{edinplus_npu._hostname}",
    # )
    
    # # Get latest system information from the NPU
    await edinplus_npu.async_edinplus_check_systeminfo()
    
    # Ensure that all the devices are up to date on initialisation (i.e. scan for all connected devices)
    #await edinplus_npu.discover(entry)
    LOGGER.debug("Completed discover")
    
    # Monitor the TCP connection for any changes
    await edinplus_npu.monitor(hass)
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