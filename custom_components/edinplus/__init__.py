"""The eDIN+ (by Mode Lighting) HomeAssistant integration"""
from __future__ import annotations

import logging

# Import constants
from .const import *

LOGGER = logging.getLogger(__name__)

from .edinplus import EdinPlusConfig, edinplus_NPU_instance

# List of platforms to support. There should be a matching .py file for each,
# eg <light.py> and <sensor.py>
PLATFORMS: list[str] = ["sensor","light","switch","button","binary_sensor","scene"]

async def async_setup_entry(hass, entry) -> bool:
    """Set up NPU from config entry."""
    # Build a config and hub instance that is HA-agnostic.
    tcp_port = entry.data.get("tcp_port", DEFAULT_TCP_PORT)  # Default to 26 if not specified
    config = EdinPlusConfig(
        hostname=entry.data["host"],
        tcp_port=tcp_port,
        use_chan_to_scn_proxy=entry.data.get("use_chan_to_scn_proxy", True),
        keep_alive_interval=entry.data.get("keep_alive_interval", DEFAULT_KEEP_ALIVE_INTERVAL),
        keep_alive_timeout=entry.data.get("keep_alive_timeout", DEFAULT_KEEP_ALIVE_TIMEOUT),
        systeminfo_interval=entry.data.get("systeminfo_interval", DEFAULT_SYSTEMINFO_INTERVAL),
        reconnect_delay=entry.data.get("reconnect_delay", DEFAULT_RECONNECT_DELAY),
        max_reconnect_delay=entry.data.get("max_reconnect_delay", DEFAULT_MAX_RECONNECT_DELAY),
        auto_suggest_areas=entry.data.get("auto_suggest_areas", True),
    )
    edinplus_npu = edinplus_NPU_instance(config)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = edinplus_npu
    
    LOGGER.info(f"[{entry.data['host']}] Setting up eDIN+ NPU")
    
    # Start TCP connection and background monitoring first
    await edinplus_npu.start()
    LOGGER.debug(f"[{entry.data['host']}] TCP connection established")
    
    # Fetch system info and run discovery
    await edinplus_npu.async_edinplus_check_systeminfo()
    LOGGER.info(
        f"[{entry.data['host']}] Discovery completed: {len(edinplus_npu.lights)} lights, "
        f"{len(edinplus_npu.switches)} switches, {len(edinplus_npu.buttons)} buttons, "
        f"{len(edinplus_npu.binary_sensors)} binary sensors, {len(edinplus_npu.scenes)} scenes"
    )
    LOGGER.debug(f"[{entry.data['host']}] TCP monitoring started")

    # This creates each HA object for each platform your device requires (e.g. light, switch)
    # It's done by calling the `async_setup_entry` function in each platform module.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    LOGGER.info(f"[{entry.data['host']}] eDIN+ integration setup completed successfully")
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Unload a config entry."""
    # Stop background TCP monitoring and close the connection for this hub.
    npu = hass.data[DOMAIN].get(entry.entry_id)
    if npu is not None:
        try:
            await npu.stop()
        except Exception:  # best-effort shutdown
            LOGGER.debug("[%s] Error while stopping NPU instance", entry.data["host"])

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        LOGGER.info(f"[{entry.data['host']}] eDIN+ NPU unloaded successfully")

    return unload_ok