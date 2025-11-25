"""Core eDIN+ TCP/HTTP client used by the HomeAssistant integration.

This module intentionally contains **no** HomeAssistant dependencies so it can
be reused as a standalone library. HomeAssistant specific glue code lives in
the platform files (e.g. ``light.py``, ``switch.py``).
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

import aiohttp

from .const import *
from .scene import edinplus_scene_instance

LOGGER = logging.getLogger(__name__)

TcpCallback = Callable[[], None]


async def tcp_send_message(writer: asyncio.StreamWriter, message: str) -> None:
    """Send a single line message over the TCP stream.

    The NPU expects ASCII text terminated with ``;`` and ``"\n"``.
    """

    LOGGER.debug("TCP TX: %r", message)
    writer.write(message.encode())
    await writer.drain()


async def tcp_receive_message(reader: asyncio.StreamReader) -> str:
    """Read a single line message from the TCP stream.

    Returns an empty string on EOF.
    """

    data = await reader.readline()
    if not data:
        return ""
    return data.decode()

# Async method of interrogating NPU via HTTP. 
# Used for discovery only
async def async_retrieve_from_npu(endpoint):
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint) as resp:
            response = await resp.text()
    return response

@dataclass
class EdinPlusConfig:
    """Configuration for an NPU connection and polling behaviour."""

    hostname: str
    tcp_port: int = DEFAULT_TCP_PORT
    use_chan_to_scn_proxy: bool = True
    keep_alive_interval: int = DEFAULT_KEEP_ALIVE_INTERVAL  # seconds; NPU drops after ~3600s idle
    keep_alive_timeout: int = DEFAULT_KEEP_ALIVE_TIMEOUT
    systeminfo_interval: int = DEFAULT_SYSTEMINFO_INTERVAL
    reconnect_delay: int = DEFAULT_MIN_RECONNECT_DELAY
    max_reconnect_delay: int = DEFAULT_MAX_RECONNECT_DELAY
    auto_suggest_areas: bool = True

class edinplus_NPU_instance:
    """Connection manager for a single eDIN+ NPU.

    This class owns the TCP connection, background reader task and recovery
    logic. Callers can await ``start()``/``stop()`` and subscribe to state
    updates via the various channel / sensor instances.
    """

    def __init__(self, config: EdinPlusConfig) -> None:
        hostname = config.hostname
        LOGGER.debug("[%s] Initialising NPU instance", hostname)
        LOGGER.debug(f"[{hostname}] Configuration: TCP port={config.tcp_port}, use_chan_to_scn_proxy={config.use_chan_to_scn_proxy}, keep_alive_interval={config.keep_alive_interval}, keep_alive_timeout={config.keep_alive_timeout}, systeminfo_interval={config.systeminfo_interval}, reconnect_delay={config.reconnect_delay}, max_reconnect_delay={config.max_reconnect_delay}, auto_suggest_areas={config.auto_suggest_areas}")

        self._config: EdinPlusConfig = config
        self._hostname: str = hostname
        self._name: str = hostname
        self._tcpport: int = config.tcp_port

        self._id: str = f"edinplus-hub-{hostname.lower()}"
        # NB the endpoint should support alternative ports for http connection ideally
        self._endpoint: str = (
            f"http://{hostname}/gateway?1"
        )  # ``?1`` prevents stripping of ``?``

        # Collections populated by discovery
        self.lights: List[edinplus_dimmer_channel_instance] = []
        # These lists are populated by discovery; typed at runtime to avoid
        # forward-reference issues during module import.
        self.switches: List[Any] = []
        self.buttons: List[Any] = []
        self.binary_sensors: List[Any] = []
        self.scenes: List[edinplus_scene_instance] = []

        self.manufacturer: str = "Mode Lighting"
        self.model: str = "DIN-NPU-00-01-PLUS"
        self.tcp_version: Optional[str] = None
        self.serial_num: Optional[str] = None
        self.edit_stamp: Optional[str] = None
        self.adjust_stamp: Optional[str] = None
        self.info_what_names: Optional[str] = None
        self.info_what_levels: Optional[str] = None

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

        self._monitor_task: Optional[asyncio.Task[Any]] = None
        self._keepalive_task: Optional[asyncio.Task[Any]] = None
        self._systeminfo_task: Optional[asyncio.Task[Any]] = None
        self._stop_event: asyncio.Event = asyncio.Event()

        self._use_chan_to_scn_proxy: bool = config.use_chan_to_scn_proxy
        self.chan_to_scn_proxy: Dict[str, int] = {}
        self.chan_to_scn_proxy_fadetime: Dict[str, int] = {}
        self.areas: Dict[int, str] = {}

        self.online: bool = False
        self.comms_retry_attempts: int = 0
        self.comms_max_retry_attempts: int = DEFAULT_MAX_RETRY_ATTEMPTS
        self._reconnect_delay: float = config.reconnect_delay

        # Timestamp of the last successfully received TCP message from the NPU
        self.last_message_received: Optional[datetime] = None
        # Timestamp of the last keep-alive acknowledgement (!OK;) from the NPU
        self.last_keepalive_ack: Optional[datetime] = None

        # Callbacks for button / input events (device automation in HA will
        # subscribe via a thin wrapper but this module stays generic).
        self._button_event_callbacks: Set[
            Callable[[Dict[str, Any]], Awaitable[None]]
        ] = set()

        LOGGER.debug("[%s] NPU instance initialised", hostname)

    # ------------------------------------------------------------------
    # Event subscription (used by HA device triggers via wrapper code)
    # ------------------------------------------------------------------

    def register_button_event_callback(
        self, callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Register an async callback for button / input events.

        The callback receives a payload with at least ``device_uuid`` and
        ``type`` describing the event.
        """

        self._button_event_callbacks.add(callback)

    def remove_button_event_callback(
        self, callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Remove a previously registered button / input callback."""

        self._button_event_callbacks.discard(callback)

    async def _dispatch_button_event(self, payload: Dict[str, Any]) -> None:
        """Dispatch a button or input event to all subscribers."""

        if not self._button_event_callbacks:
            return

        for cb in list(self._button_event_callbacks):
            try:
                await cb(payload)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.error("[%s] Button event callback failed: %s", self._hostname, exc)

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------

    async def async_test_connection(self) -> bool:
        """Test connectivity to the NPU via both HTTP and TCP.

        Returns True if both HTTP (port 80) and TCP (configured port) are accessible.
        Returns False if either connection fails.
        """
        
        # Test HTTP connectivity
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{self._hostname}/info?what=names",
                    timeout=aiohttp.ClientTimeout(total=CONNECTION_TEST_TIMEOUT_HTTP)
                ) as resp:
                    if resp.status != 200:
                        LOGGER.error(
                            "[%s] HTTP connection failed with status %d",
                            self._hostname,
                            resp.status,
                        )
                        return False
                    LOGGER.debug("[%s] HTTP connection test successful", self._hostname)
        except asyncio.TimeoutError:
            LOGGER.error("[%s] HTTP connection timed out", self._hostname)
            return False
        except aiohttp.ClientError as exc:
            LOGGER.error("[%s] HTTP connection failed: %s", self._hostname, exc)
            return False
        except Exception as exc:
            LOGGER.error("[%s] Unexpected error testing HTTP: %s", self._hostname, exc)
            return False

        # Test TCP connectivity
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._hostname, self._tcpport),
                timeout=CONNECTION_TEST_TIMEOUT_TCP
            )
            LOGGER.debug("[%s] TCP connection test successful", self._hostname)
            
            # Clean up test connection
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                LOGGER.warning("[%s] Error while closing test TCP connection, skipping close and relying on NPU to terminate", self._hostname)
                pass
                
        except asyncio.TimeoutError:
            LOGGER.error(
                "[%s] TCP connection to port %d timed out",
                self._hostname,
                self._tcpport,
            )
            return False
        except OSError as exc:
            LOGGER.error(
                "[%s] TCP connection to port %d failed: %s",
                self._hostname,
                self._tcpport,
                exc,
            )
            return False
        except Exception as exc:
            LOGGER.error(
                "[%s] Unexpected error testing TCP: %s",
                self._hostname,
                exc,
            )
            return False

        return True

    async def start(self) -> None:
        """Connect to the NPU and start background monitoring.

        This method is idempotent.
        """

        if self._monitor_task and not self._monitor_task.done():
            # LOGGER.debug("[%s] NPU monitor already running", self._hostname)
            return

        self._stop_event.clear()
        await self._ensure_connected()

        loop = asyncio.get_running_loop()
        LOGGER.debug("[%s] Starting monitor, keep-alive, and systeminfo loops", self._hostname)
        self._monitor_task = loop.create_task(self._monitor_loop(), name=f"edinplus-monitor-{self._hostname}")
        self._keepalive_task = loop.create_task(self._keepalive_loop(), name=f"edinplus-keepalive-{self._hostname}")
        self._systeminfo_task = loop.create_task(self._systeminfo_loop(), name=f"edinplus-systeminfo-{self._hostname}")

    async def stop(self) -> None:
        """Stop background tasks and close the TCP connection."""

        self._stop_event.set()

        for task in (self._monitor_task, self._keepalive_task, self._systeminfo_task):
            if task is not None:
                task.cancel()

        self._monitor_task = None
        self._keepalive_task = None
        self._systeminfo_task = None

        if self.writer is not None:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as exc:  
                # NB This will result in a zombie connection on the NPU side if not closed properly
                LOGGER.warning("[%s] Writer object was not closed properly during the stop, this will use up a TCP connection on the NPU. Exception details: %s", self._hostname, exc)

        self.reader = None
        self.writer = None
        self.online = False
    
    async def discover(self) -> None:
        # Discover areas first
        self.areas = await self.async_edinplus_discover_areas()
        # Discover all lighting channels on devices connected to NPU
        (
            self.lights,
            self.switches,
            self.buttons,
            self.binary_sensors,
        ) = await self.async_edinplus_discover_channels()
        # Discover all scenes on the NPU
        self.scenes = await self.async_edinplus_discover_scenes()
        # Search to see if a channel has a unique scene with just it in - if so, toggle that scene rather than the channel (as keeps NPU happier!)
        (
            self.chan_to_scn_proxy,
            self.chan_to_scn_proxy_fadetime,
        ) = await self.async_edinplus_map_chans_to_scns()
        # Get the status for each light
        for light in self.lights:
            await light.tcp_force_state_inform()
        # Get the status for each switch
        for switch in self.switches:
            await switch.tcp_force_state_inform()
        # Get the status for each binary sensor
        for binary_sensor in self.binary_sensors:
            await binary_sensor.tcp_force_state_inform()
            
    async def async_edinplus_check_systeminfo(self) -> None:
        # Download and store the NPU configuration endpoints
        self.info_what_names = await async_retrieve_from_npu(
            f"http://{self._hostname}/info?what=names"
        )
        self.info_what_levels = await async_retrieve_from_npu(
            f"http://{self._hostname}/info?what=levels"
        )
        
        # Check system information from the NPU
        # This is used to get the serial number, edit and adjust timestamps
        # try:
        if not self.info_what_levels:
            LOGGER.debug("[%s] No system info available yet", self._hostname)
            return

        systeminfo = re.findall(r"!SYSTEMID,(\d+),(\d+-\d+),(\d+-\d+)", self.info_what_levels)
        if systeminfo and len(systeminfo[0]) == 3:
            serial_num, edit_stamp, adjust_stamp = systeminfo[0]
            if self.edit_stamp != edit_stamp or self.adjust_stamp != adjust_stamp:
                LOGGER.info(f"[{self._hostname}] NPU configuration has changed - triggering rediscovery")
                self.serial_num = serial_num
                self.edit_stamp = edit_stamp
                self.adjust_stamp = adjust_stamp
                LOGGER.debug(f"[{self._hostname}] Serial number: {self.serial_num}, Edit timestamp: {self.edit_stamp}, Adjust timestamp: {self.adjust_stamp}")
                
                LOGGER.debug(f"[{self._hostname}] Running discovery of channels, areas and scenes on the NPU")
                await self.discover()
            else:
                LOGGER.debug(f"[{self._hostname}] NPU configuration unchanged - no rediscovery needed")
        else:
            LOGGER.error(f"[{self._hostname}] Could not find serial number of the eDIN+ system. Please report this issue to the developer of the integration.")
            LOGGER.error(f"[{self._hostname}] Raw data: {self.info_what_levels}")
        # except Exception as e:
        #     LOGGER.error(f"Exception occurred while parsing system info: {e}")
        #     LOGGER.error(self.info_what_levels)


    async def _ensure_connected(self) -> None:
        """Ensure there is an active TCP connection to the NPU.

        Handles initial connection and re-connects with exponential backoff on
        failure. This method is safe to call repeatedly.
        """

        if self.online and self.reader is not None and self.writer is not None:
            return

        while not self._stop_event.is_set():
            LOGGER.debug(
                "[%s] Establishing TCP connection to %s on port %s",
                self._hostname,
                self._hostname,
                self._tcpport,
            )
            try:
                reader, writer = await asyncio.open_connection(
                    self._hostname, self._tcpport
                )
                self.reader = reader
                self.writer = writer
                self.online = True
                self.comms_retry_attempts = 0
                self._reconnect_delay = self._config.reconnect_delay

                # Register to receive all events
                await tcp_send_message(self.writer, "$EVENTS,1;")
                output = await tcp_receive_message(self.reader)

                if output.rstrip() == "":
                    LOGGER.error(
                        "[%s] No TCP response from NPU after registration. Please restart the NPU (Configuration -> Tools -> Reinitialise system -> Reboot system) if the problem persists.",
                        self._hostname,
                    )
                elif output.rstrip() == "!GATRDY;":
                    LOGGER.info("[%s] TCP connection established successfully (GATRDY)", self._hostname)
                    return
                else:
                    LOGGER.error(
                        "[%s] TCP connection not ready; received message: %s",
                        self._hostname,
                        output,
                    )
            except Exception as exc:  # pragma: no cover - network error path
                LOGGER.error(
                    "[%s] Unable to establish TCP connection: %s",
                    self._hostname,
                    exc,
                )

            self.online = False
            LOGGER.info(
                "[%s] Retrying TCP connection in %.1fs",
                self._hostname,
                self._reconnect_delay,
            )
            try:
                # Wait for _reconnect_delay seconds or until _stop_event is set (connection has been made)
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._reconnect_delay)
                return
            except asyncio.TimeoutError:
                LOGGER.error(
                    "[%s] Reconnect delay elapsed, retrying TCP connection",
                    self._hostname,
                )
                pass

            self._reconnect_delay = min(
                self._reconnect_delay * 2, self._config.max_reconnect_delay
            )

    async def _keepalive_loop(self) -> None:
        """Periodic keep-alive that also validates the connection.

        Sends keep-alive messages without reading directly from the TCP stream.
        The monitor loop processes all incoming data including !OK; responses.
        We validate that an !OK; response is received within the timeout period.
        """

        interval = self._config.keep_alive_interval
        LOGGER.debug("[%s] Keep-alive loop starting with interval=%s", self._hostname, interval)

        if interval <= 0:
            LOGGER.error("[%s] Invalid keep-alive interval (%s); keep-alive loop disabled", self._hostname, interval)
            return
        
        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                    # Stop requested while waiting
                    break
                except asyncio.TimeoutError:
                    # Normal wake-up after interval expiry
                    pass

                if not self.online or self.writer is None or self.reader is None:
                    continue

                # Record the time before sending keep-alive
                keepalive_sent_at = datetime.now(timezone.utc)
                
                LOGGER.debug("[%s] Sending TCP keep-alive", self._hostname)
                try:
                    # Only send the keep-alive; the monitor loop exclusively owns
                    # reading from the TCP stream to avoid concurrent reads.
                    await tcp_send_message(self.writer, "$OK;")
                except (RuntimeError, OSError) as exc:
                    self.comms_retry_attempts += 1
                    LOGGER.error(
                        "[%s] Keep-alive send failed (%s) attempt %s/%s",
                        self._hostname,
                        exc,
                        self.comms_retry_attempts,
                        self.comms_max_retry_attempts,
                    )
                    
                    if self.comms_retry_attempts >= self.comms_max_retry_attempts:
                        LOGGER.warning(
                            "[%s] Max keep-alive retries reached; dropping TCP connection",
                            self._hostname,
                        )
                        if self.writer is not None:
                            try:
                                self.writer.close()
                                await self.writer.wait_closed()
                            except Exception:
                                pass
                        self.reader = None
                        self.writer = None
                        self.online = False
                        self.comms_retry_attempts = 0
                    continue

                # Wait for the response to arrive (processed by monitor loop)
                # Check if we received an !OK; within the timeout period
                await asyncio.sleep(self._config.keep_alive_timeout)
                
                if self.last_keepalive_ack is None:
                    # No !OK; ever received yet
                    self.comms_retry_attempts += 1
                    LOGGER.error(
                        "[%s] No keep-alive acknowledgement received (attempt %s/%s)",
                        self._hostname,
                        self.comms_retry_attempts,
                        self.comms_max_retry_attempts,
                    )
                else:
                    # Check if the last !OK; was recent enough (after we sent this keep-alive)
                    time_since_ack = (datetime.now(timezone.utc) - self.last_keepalive_ack).total_seconds()
                    expected_max_delay = self._config.keep_alive_timeout + 1.0  # Add 1s grace period
                    
                    if self.last_keepalive_ack >= keepalive_sent_at:
                        # Received fresh acknowledgement
                        self.comms_retry_attempts = 0
                        LOGGER.debug(
                            "[%s] Keep-alive acknowledged",
                            self._hostname,
                        )
                    elif time_since_ack <= expected_max_delay:
                        # Recent enough acknowledgement (from previous keep-alive)
                        self.comms_retry_attempts = 0
                        LOGGER.debug(
                            "[%s] Keep-alive implicitly acknowledged (recent !OK; received %.1fs ago)",
                            self._hostname,
                            time_since_ack,
                        )
                    else:
                        # No recent acknowledgement
                        self.comms_retry_attempts += 1
                        LOGGER.error(
                            "[%s] Keep-alive timeout - no !OK; received within %.1fs (attempt %s/%s)",
                            self._hostname,
                            self._config.keep_alive_timeout,
                            self.comms_retry_attempts,
                            self.comms_max_retry_attempts,
                        )

                if self.comms_retry_attempts >= self.comms_max_retry_attempts:
                    LOGGER.warning(
                        "[%s] Max keep-alive retries reached; dropping TCP connection",
                        self._hostname,
                    )
                    if self.writer is not None:
                        try:
                            self.writer.close()
                            await self.writer.wait_closed()
                        except Exception:
                            pass
                    self.reader = None
                    self.writer = None
                    self.online = False
                    self.comms_retry_attempts = 0
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancel
            LOGGER.debug("[%s] Keep-alive loop cancelled", self._hostname)
        except Exception as exc:
            LOGGER.error("[%s] Keep-alive loop crashed: %r", self._hostname, exc)

    async def _systeminfo_loop(self) -> None:
        """Periodically refresh system information and trigger rediscovery."""

        interval = self._config.systeminfo_interval

        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=interval
                    )
                    # Stop requested while waiting
                    if self._stop_event.is_set():
                        break
                except asyncio.TimeoutError:
                    # Normal wake-up after interval expiry
                    pass

                if not self.online:
                    continue

                await self.async_edinplus_check_systeminfo()
        except asyncio.CancelledError:  # pragma: no cover
            LOGGER.debug("[%s] Systeminfo loop cancelled", self._hostname)
        except Exception as exc:
            LOGGER.error("[%s] Systeminfo loop crashed: %r", self._hostname, exc)
    

    async def async_response_handler(self, response: str) -> None:
        """Handle any messages read from the TCP stream."""

        if response != "":
            # Record the time of the last valid message from the NPU
            self.last_message_received = datetime.now(timezone.utc)
            # LOGGER.debug("[%s] TCP RX: %s", self._hostname, response)
            
            # Handle !OK; response (sent as part of keep-alive acknowledgement)
            if "!OK;" in response:
                self.last_keepalive_ack = datetime.now(timezone.utc)
                LOGGER.debug(f"[{self._hostname}] Keep-alive received: {response}")
                return
            
            response_type = response.split(',')[0]
            # Parse response and determine what to do with it
            if response_type == "!GATRDY":
                LOGGER.warning(f"[{self._hostname}] GATRDY received unexpectedly by async_response_handler: {response}")
            if response_type == "!VERSION":
                version = response.split(',')[1].split(';')[0]
                self.tcp_version = version
                LOGGER.info(f"[{self._hostname}] NPU firmware version: {version}")
            elif response_type == "!INPSTATE":
                # !INPSTATE means a contact module press.
                address = int(response.split(',')[1])
                channel = int(response.split(',')[3])
                newstate_numeric = int(response.split(',')[4][:3])
                newstate = NEWSTATE_TO_BUTTONEVENT[newstate_numeric]
                uuid = f"edinplus-{self.serial_num}-{address}-{channel}"
                found_binary_sensor_channel = False
                binary_sensor_discovery_in_progress = False # Set to false by default to capture case where no binary sensors have been initialised yet
                for binary_sensor in self.binary_sensors:
                    if binary_sensor.channel == channel and binary_sensor._address == address:
                        found_binary_sensor_channel = True
                        LOGGER.debug(f"[{self._hostname}] Binary sensor {binary_sensor._address}-{binary_sensor.channel} state updated to {newstate_numeric > 0}")
                        if (binary_sensor._is_on == None):
                            binary_sensor_discovery_in_progress = True
                        else:
                            binary_sensor_discovery_in_progress = False
                        
                        binary_sensor._is_on = (newstate_numeric > 0)
                        for callback in binary_sensor._callbacks:
                            callback()
                if not found_binary_sensor_channel:
                    LOGGER.warning(f"[{self._hostname}] Binary sensor without corresponding entity found; address {address}, channel {channel}")

                if not binary_sensor_discovery_in_progress:
                    LOGGER.debug(
                        "[%s] Dispatching input event for %s (%s)",
                        self._hostname,
                        uuid,
                        newstate,
                    )
                    await self._dispatch_button_event(
                        {
                            "device_uuid": uuid,
                            "type": newstate,
                        }
                    )


            elif response_type == "!BTNSTATE":
                # !BTNSTATE means a button/keypad press, meaning an event needs to be triggered with the relevant information
                # This is then processed using device_trigger.py to reassign this event (which is just JSON) to a device in the HA GUI.
                # NB Key difference is that a keypad is presented as a single device in HA with up to 10 possible buttons, while each individual contact input is presented as its own device in HA (i.e. an 8 channel CI module would result in 8 devices), as the channels aren't necessarily in the same room
                address = int(response.split(',')[1])
                channel = int(response.split(',')[3])

                # NB need to exclude channel in place of whole keypad
                newstate_numeric = int(response.split(',')[4][:3])
                newstate = f"Button {channel} {NEWSTATE_TO_BUTTONEVENT[newstate_numeric]}"
                uuid = f"edinplus-{self.serial_num}-{address}-1"  # Channel is always 1 in the UUID for a keypad

                LOGGER.debug(
                    "[%s] Dispatching keypad event for %s (%s)",
                    self._hostname,
                    uuid,
                    newstate,
                )
                await self._dispatch_button_event(
                    {
                        "device_uuid": uuid,
                        "type": newstate,
                    }
                )

            elif (response_type == '!CHANFADE')or(response_type == '!CHANLEVEL'):
                LOGGER.debug(f"[{self._hostname}] Channel fade/level received: {response}")
                # CHANFADE/LEVEL corresponds to a lighting channel
                for light in self.lights:
                    if light.channel == int(response.split(',')[3]) and light._dimmer_address == int(response.split(',')[1]):
                        LOGGER.debug(f"[{self._hostname}] Light {light._dimmer_address}-{light.channel} brightness updated to {int(response.split(',')[4])}")
                        light._is_on = (int(response.split(',')[4]) > 0)
                        light._brightness = int(response.split(',')[4])

                        for callback in light._callbacks:
                            callback()
                for switch in self.switches:
                    if switch.channel == int(response.split(',')[3]) and switch._address == int(response.split(',')[1]):
                        LOGGER.debug(f"[{self._hostname}] Switch {switch._address}-{switch.channel} state updated to {(int(response.split(',')[4]) > 0)}")
                        switch._is_on = (int(response.split(',')[4]) > 0)

                        for callback in switch._callbacks:
                            callback()
                        # light.update_callback()
                        
            # elif (response_type == '!INPERR'):
            #     # Process any errors from the eDIN+ system and pass to the HA logs
            #     addr = int(response.split(',')[1])
            #     dev = DEVCODE_TO_PRODNAME[int(response.split(',')[2])]
            #     chan_num = int(response.split(',')[3])
            #     statuscode = int(response.split(',')[4].split(';')[0])
            #     if statuscode != 0:
            #         LOGGER.warning(f"[{self._hostname}] Module error on input channel number [{chan_num}] (found on device {dev} @ address [{addr}]: {STATUSCODE_TO_SUMMARY[statuscode]} ({STATUSCODE_TO_DESC[statuscode]})")
            elif(response_type == '!MODULEERR'):
                # Process any errors from the eDIN+ system and pass to the HA logs
                addr = int(response.split(',')[1])
                dev = DEVCODE_TO_PRODNAME[int(response.split(',')[2])]
                statuscode = int(response.split(',')[3].split(';')[0])
                # Status code 0 = all ok!
                if statuscode != 0:
                    LOGGER.warning(f"[{self._hostname}] Module error on {dev} @ address [{addr}]: {STATUSCODE_TO_SUMMARY[statuscode]} ({STATUSCODE_TO_DESC[statuscode]}")
            elif(response_type == '!CHANERR'):
                # Process any errors from the eDIN+ system and pass to the HA logs
                addr = int(response.split(',')[1])
                dev = DEVCODE_TO_PRODNAME[int(response.split(',')[2])]
                chan_num = int(response.split(',')[3])
                statuscode = int(response.split(',')[4].split(';')[0])
                if statuscode != 0:
                    LOGGER.warning(f"[{self._hostname}] Module error on channel number [{chan_num}] (found on device {dev} @ address [{addr}]: {STATUSCODE_TO_SUMMARY[statuscode]} ({STATUSCODE_TO_DESC[statuscode]})")
            elif(response_type == '!OK'):
                LOGGER.debug(f"[{self._hostname}] NPU acknowledgement: {response}") # We don't currently do anything with this, but log for debugging. In future maybe track last ack time for keep-alive validation?
            elif(response_type == '!SCNOFF'):
                LOGGER.debug(f"[{self._hostname}] NPU confirmed scene {response.split(',')[1].split(';')[0]} is now off")
            elif(response_type == '!SCNRECALL'):
                LOGGER.debug(f"[{self._hostname}] NPU confirmed scene {response.split(',')[1].split(';')[0]} has been recalled (i.e. is on)")
            elif(response_type == '!SCNSTATE'):
                LOGGER.debug(f"[{self._hostname}] NPU confirmed scene {response.split(',')[1]} has been set to {round(int(response.split(',')[3])/2.55)}% of max scene brightness")
            else:
                LOGGER.debug(f"[{self._hostname}] Unknown TCP response: {response}")

    async def _monitor_loop(self) -> None:
        """Continuously read from the TCP stream and dispatch messages.

        This loop self-recovers by re-establishing the TCP connection whenever
        the reader hits EOF or raises an error.
        """

        try:
            while not self._stop_event.is_set():
                await self._ensure_connected()
                if not self.online or self.reader is None:
                    # Connection could not be established and stop was requested
                    await asyncio.sleep(1)
                    continue

                try:
                    response = await tcp_receive_message(self.reader)
                except (asyncio.IncompleteReadError, OSError) as exc:
                    LOGGER.error(
                        "[%s] TCP read error: %s – will reconnect",
                        self._hostname,
                        exc,
                    )
                    self.online = False
                    if self.writer is not None:
                        try:
                            self.writer.close()
                            await self.writer.wait_closed()
                        except Exception:
                            pass
                    self.reader = None
                    self.writer = None
                    continue

                if response == "":
                    # EOF – drop connection and try again
                    LOGGER.warning(
                        "[%s] TCP stream closed by remote host – reconnecting",
                        self._hostname,
                    )
                    self.online = False
                    if self.writer is not None:
                        try:
                            self.writer.close()
                            await self.writer.wait_closed()
                        except Exception:
                            pass
                    self.reader = None
                    self.writer = None
                    continue

                await self.async_response_handler(response)
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancel
            LOGGER.debug("[%s] Monitor loop cancelled", self._hostname)
        except Exception as exc:
            LOGGER.error("[%s] Monitor loop crashed: %r", self._hostname, exc)


    async def async_edinplus_discover_channels(self):
        """Discover channels using the ``info?what=names`` payload."""

        dimmer_channel_instances: List[edinplus_dimmer_channel_instance] = []
        relay_channel_instances: List[edinplus_relay_channel_instance] = []
        relay_pulse_instances: List[edinplus_relay_pulse_instance] = []
        binary_sensor_instances: List[edinplus_input_binary_sensor_instance] = []

        NPU_raw = self.info_what_names

        NPU_data = NPU_raw.splitlines()

        areas_csv = [idx for idx in NPU_data if idx.startswith("AREA")]

        areas = {}
        channels = []
        for area in areas_csv:
            # Parsing expected format of Area,AreaNum,AreaName
            areas[int(area.split(',')[1])] = area.split(',')[2]


        # Lighting channels
        channels_csv = [idx for idx in NPU_data if idx.startswith("CHAN")]
        for channel in channels_csv:
            # Parsing expected format of Channel,Address,DevCode,ChanNum,AreaNum,ChanName
            channel_entity = {}
            channel_entity['address'] = int(channel.split(',')[1])
            channel_entity['channel'] = int(channel.split(',')[3])
            channel_entity['area'] = areas[int(channel.split(',')[4])]
            channel_entity['devcode'] = int(channel.split(',')[2])
            channel_entity['model'] = DEVCODE_TO_PRODNAME[channel_entity['devcode']]
            channel_entity['name'] = channel.split(',')[5]
            if not channel_entity['name']:
                    channel_entity['name'] = f"Unnamed {channel_entity['model']} addr {channel_entity['address']} chan {channel_entity['channel']}"
            
            # We now only add output channels selectively, as relays don't behave the same as lights
            if channel_entity['devcode'] == 12: # 8 channel dimmer module
                dimmer_channel_instances.append(edinplus_dimmer_channel_instance(channel_entity['address'],channel_entity['channel'],f"{channel_entity['area']} {channel_entity['name']}",channel_entity['area'],channel_entity['model'],channel_entity['devcode'],self))
            elif channel_entity['devcode'] == 15: # I/O module
                dimmer_channel_instances.append(edinplus_dimmer_channel_instance(channel_entity['address'],channel_entity['channel'],f"{channel_entity['area']} {channel_entity['name']}",channel_entity['area'],channel_entity['model'],channel_entity['devcode'],self))
            elif channel_entity['devcode'] == 14: # 4 channel dimmer module
                LOGGER.warning(f"[{self._hostname}] Unsupported output entity of type {DEVCODE_TO_PRODNAME[channel_entity['devcode']]} found in area {channel_entity['area']} as {channel_entity['name']}, channel number {channel_entity['channel']}. Adding to HomeAssistant for now.")
                dimmer_channel_instances.append(edinplus_dimmer_channel_instance(channel_entity['address'],channel_entity['channel'],f"{channel_entity['area']} {channel_entity['name']}",channel_entity['area'],channel_entity['model'],channel_entity['devcode'],self))
            elif channel_entity['devcode'] == 16: # 4x5A Relay module
                relay_channel_instances.append(edinplus_relay_channel_instance(channel_entity['address'],channel_entity['channel'],f"{channel_entity['area']} {channel_entity['name']}",channel_entity['area'],channel_entity['model'],channel_entity['devcode'],self))
                relay_pulse_instances.append(edinplus_relay_pulse_instance(channel_entity['address'],channel_entity['channel'],f"{channel_entity['area']} {channel_entity['name']} pulse toggle",channel_entity['area'],channel_entity['model'],channel_entity['devcode'],self))
            else:
                LOGGER.warning(f"[{self._hostname}] Incompatible/Unknown output entity of type {DEVCODE_TO_PRODNAME[channel_entity['devcode']]} found in area {channel_entity['area']} as {channel_entity['name']}, channel number {channel_entity['channel']}. Not adding to HomeAssistant")

        # Contact modules
        inputs_csv = [idx for idx in NPU_data if idx.startswith("INPSTATE")]
        input_entities = []
        for input in inputs_csv:
            # Parsing expected format of Channel,Address,DevCode,ChanNum,AreaNum,ChanName
            input_entity = {}
            input_entity['address'] = int(input.split(',')[1])
            input_entity['channel'] = int(input.split(',')[3])
            input_entity['id'] = f"edinplus-{self.serial_num}-{input_entity['address']}-{input_entity['channel']}"
            # For area on keypad this has to be matched to the PLATE
            input_entity['devcode'] = int(input.split(',')[2])
            input_entity['model'] = DEVCODE_TO_PRODNAME[input_entity['devcode']]
            if input_entity['devcode'] == 9: # Contact input module
                input_entity['name'] = input.split(',')[5]
                if not input_entity['name']:
                    input_entity['name'] = f"Unnamed {input_entity['model']} addr {input_entity['address']} chan {input_entity['channel']}"
                input_entity['area'] = areas[int(input.split(',')[4])]
                input_entity['full_name'] = f"{input_entity['area']} {input_entity['name']}"
                binary_sensor_instances.append(edinplus_input_binary_sensor_instance(input_entity['address'],input_entity['channel'],f"{input_entity['area']} {input_entity['name']}",input_entity['area'],input_entity['model'],input_entity['devcode'],self))
            elif input_entity['devcode'] == 15: # I/O module
                input_entity['name'] = input.split(',')[5]
                if not input_entity['name']:
                    input_entity['name'] = f"Unnamed {input_entity['model']} addr {input_entity['address']} chan {input_entity['channel']}"
                input_entity['area'] = areas[int(input.split(',')[4])]
                input_entity['full_name'] = f"{input_entity['area']} {input_entity['name']}"
                binary_sensor_instances.append(edinplus_input_binary_sensor_instance(input_entity['address'],input_entity['channel'],f"{input_entity['area']} {input_entity['name']}",input_entity['area'],input_entity['model'],input_entity['devcode'],self))
            elif input_entity['devcode'] == 2: # Wall plate
                # NB there is currently no way of telling how many buttons a wall plate has from this discovery method - this is a known issue that has been discussed with Mode Lighting
                # Consequently we only store this once for "channel 1" - in reality the CSV file has channel 1 and 2, irrespective of how many buttons there actually are on the keypad
                if input_entity['channel'] != 1:
                    continue
                # The name also has to be matched to the PLATE name if it exists (else do unnamed wall plate address #)
                plate_info = re.findall(rf"PLATE,{input_entity['address']},{input_entity['devcode']},(\d+),([\w ]+)?",NPU_raw)
                if not plate_info:
                    LOGGER.warning(f"[{self._hostname}] No plate information found for address {input_entity['address']} and devcode {input_entity['devcode']}. This is likely a bug in the eDIN+ system, please report to Mode Lighting.")
                    plate_name = f"Unnamed Wall Plate address {input_entity['address']}"
                    plate_area = "Unknown area"
                else:
                    plate_name = plate_info[0][1] 
                    plate_area = areas[int(plate_info[0][0])]

                input_entity['name'] = plate_name
                input_entity['area'] = plate_area
                # Keypads can't have names assigned via the eDIN+ interface
                input_entity['full_name'] = f"{input_entity['area']} {input_entity['name']} keypad" # This needs to be reviewed - a keypad should only appear once, rather than having each individual button listed as a device (although this adds complexity to device_trigger as possible events need to be extended as e.g. Release-off button1, release-off button2 etc)
            else:
                # This should probably go through error handling rather than being blindly created, as it's an unknown device, and almost certainly won't work properly with the device trigger
                input_entity['name'] = input.split(',')[5]
                input_entity['area'] = areas[int(input.split(',')[4])]
                # input_entity['full_name'] = f"{input_entity['area']} {input_entity['name']} switch"
                LOGGER.warning(f"[{self._hostname}] Unknown input entity of type {DEVCODE_TO_PRODNAME[input_entity['devcode']]} found in area {input_entity['area']} as {input_entity['name']} with id {input_entity['id']}. Not adding to HomeAssistant.")
                continue
            
            input_entities.append(input_entity)

        for input_entity in input_entities:
            if input_entity['devcode'] not in [1, 2, 9, 15]:  # Only support LCD wall plate (1), button plates (2), contact input modules (9), and I/O modules (15)
                LOGGER.warning(f"[{self._hostname}] Unknown input entity of type {DEVCODE_TO_PRODNAME[input_entity['devcode']]} found in area {input_entity['area']} as {input_entity['name']} with id {input_entity['id']}. Not adding to HomeAssistant.")
                continue
            
            LOGGER.debug(f"[{self._hostname}] Input entity found: {input_entity['model']} '{input_entity['name']}' (id: {input_entity['id']})")

        LOGGER.info(f"[{self._hostname}] Channel discovery completed: {len(dimmer_channel_instances)} dimmers, {len(relay_channel_instances)} relays, {len(relay_pulse_instances)} pulse buttons, {len(binary_sensor_instances)} binary sensors")
        return dimmer_channel_instances,relay_channel_instances,relay_pulse_instances,binary_sensor_instances

    async def async_edinplus_discover_areas(self):
        # Discover all areas on the NPU
        areas_raw = re.findall(rf"AREA,(\d+),([\w ]+)\s",self.info_what_levels)
        
        # Convert to dictionary for easier lookup
        areas_dict = {int(area[0]): area[1] for area in areas_raw}
        
        LOGGER.info(f"[{self._hostname}] Area discovery completed: {len(areas_dict)} areas found")
        return areas_dict

    async def async_edinplus_discover_scenes(self):
        # Discover all scenes on the NPU
        # This should parse the NPU data to find scenes and create edinplus_scene_instance objects
        scene_instances = []
        
        NPU_data = self.info_what_levels
        
        scenes = re.findall(rf"SCENE,(\d+),(\d+),([\w\s\(\)&\[\]]+)\s",NPU_data)
        
        for scene in scenes:
            scene_num = int(scene[0])
            area_num = int(scene[1])
            scene_name = scene[2]

            # Create a scene instance for each discovered scene
            scene_instance = edinplus_scene_instance(scene_num, scene_name, area_num, self)
            scene_instances.append(scene_instance)
        
        LOGGER.info(f"[{self._hostname}] Scene discovery completed: {len(scene_instances)} scenes found")
        return scene_instances

    async def async_edinplus_map_chans_to_scns(self):
        # Search for any scenes that only have a single channel, and use as a proxy for channels where possible (as this works better with mode inputs)
        # Now using the info?what=levels endpoint instead, as this ensures that scenes with a level of 0% aren't mapped
        chan_to_scn_proxy = {}
        chan_to_scn_proxy_fadetime = {}
        NPU_data = self.info_what_levels

        # !Scene,SceneNum,AreaNum,SceneName
        # !ScnFade,SceneNum,Fadetime(ms)
        # !ScnChannel,SceneNum,Address,DevCode,ChanNum,Level
        possible_proxies = re.findall(rf"SCENE,(\d+),\d+,[\w\s]+SCNFADE,\d+,(\d+)[\s]+SCNCHANLEVEL,\d+,(\d+),\d+,(\d+),255\s\s",NPU_data)
        # Will return all possible proxies in sequence: Scene number, FadeTime, Address, ChanNum

        for proxy_combo in possible_proxies:
            sceneID = proxy_combo[0]
            fadeTime = proxy_combo[1]
            addr = proxy_combo[2].zfill(3)
            chan_num = proxy_combo[3].zfill(3)

            chan_to_scn_proxy[f"{addr}-{chan_num}"] = int(sceneID)
            chan_to_scn_proxy_fadetime[f"{addr}-{chan_num}"] = int(fadeTime)

        LOGGER.info(f"[{self._hostname}] Channel-to-scene proxy mapping completed: {len(chan_to_scn_proxy)} proxies found")
        LOGGER.debug(f"[{self._hostname}] Proxy mapping: {chan_to_scn_proxy}")
        return chan_to_scn_proxy,chan_to_scn_proxy_fadetime

class edinplus_relay_channel_instance:
    def __init__(self, address:int, channel: int, name: str, area: str, model: str, devcode: int, npu: edinplus_NPU_instance) -> None:
        self._address = address
        self._channel = channel
        self._id = f"edinplus-{npu.serial_num}-{self._address}-{self._channel}" # This ensures that automations etc aren't destroyed if the integration is removed and re-added, as channels will have the same unique id.
        self.name = name
        self.hub = npu
        self._callbacks = set()
        self._is_on = None
        # self._connected = True # This is from the original example documentation - shouldn't be needed as connection status is handled by the NPU
        self.model = model
        self.area = area
        self._devcode = devcode

    @property
    def channel(self):
        return self._channel

    @property
    def switch_id(self) -> str:
        """Return ID for switch."""
        return self._id
    
    @property
    def is_on(self):
        return self._is_on

    async def turn_on(self):
        await tcp_send_message(self.hub.writer,f"$ChanFade,{self._address},{self._devcode},{self._channel},255,0;")
        self._is_on = True
        LOGGER.debug(f"[{self.hub._hostname}] Relay {self._address}-{self._channel} turned on")

    async def turn_off(self):
        await tcp_send_message(self.hub.writer,f"$ChanFade,{self._address},{self._devcode},{self._channel},0,0;")
        self._is_on = False
        LOGGER.debug(f"[{self.hub._hostname}] Relay {self._address}-{self._channel} turned off")

    async def tcp_force_state_inform(self):
        # A function to force a channel to report its current status to the TCP stream
        if self.hub.writer is None or not self.hub.online:
            LOGGER.debug(f"[{self.hub._hostname}] Skipping state request for relay {self._address}-{self._channel} - not connected")
            return
        LOGGER.debug(f"[{self.hub._hostname}] Requesting state for relay {self._address}-{self._channel}")
        await tcp_send_message(self.hub.writer,f"?CHAN,{self._address},{self._devcode},{self._channel};")

    # Register and remove callback functions are from example integration - not sure if still needed
    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Switch changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

class edinplus_relay_pulse_instance:
    def __init__(self, address:int, channel: int, name: str, area: str, model: str, devcode: int, npu: edinplus_NPU_instance) -> None:
        self._address = address
        self._channel = channel
        self._id = f"edinplus-{npu.serial_num}-{self._address}-{self._channel}" # This ensures that automations etc aren't destroyed if the integration is removed and re-added, as channels will have the same unique id.
        self.name = name
        self.hub = npu
        self._callbacks = set()
        self.model = model
        self.area = area
        self._devcode = devcode
        self.pulse_time = 1000 # miliseconds; this should be configurable

    @property
    def channel(self):
        return self._channel

    @property
    def button_id(self) -> str:
        """Return ID for button."""
        return self._id

    async def press(self):
        await tcp_send_message(self.hub.writer,f"$ChanPulse,{self._address},{self._devcode},{self._channel},3,{self.pulse_time};")
        LOGGER.debug(f"[{self.hub._hostname}] Button {self._address}-{self._channel} pressed")

    # Register and remove callback functions are from example integration - not sure if still needed
    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Button changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

class edinplus_input_binary_sensor_instance:
    def __init__(self, address:int, channel: int, name: str, area: str, model: str, devcode: int, npu: edinplus_NPU_instance) -> None:
        self._address = address
        self._channel = channel
        self._id = f"edinplus-{npu.serial_num}-{self._address}-{self._channel}" # This ensures that automations etc aren't destroyed if the integration is removed and re-added, as channels will have the same unique id.
        self.name = name
        self.hub = npu
        self._callbacks = set()
        self._is_on = None
        self.model = model
        self.area = area
        self._devcode = devcode

    @property
    def channel(self):
        return self._channel

    @property
    def sensor_id(self) -> str:
        """Return ID for binary_sensor."""
        return self._id

    @property
    def is_on(self):
        return self._is_on

    async def tcp_force_state_inform(self):
        # A function to force an input channel to report its current status to the TCP stream
        if self.hub.writer is None or not self.hub.online:
            LOGGER.debug(f"[{self.hub._hostname}] Skipping state request for input {self._address}-{self._channel} - not connected")
            return
        LOGGER.debug(f"[{self.hub._hostname}] Requesting state for input {self._address}-{self._channel}")
        await tcp_send_message(self.hub.writer,f"?INP,{self._address},{self._devcode},{self._channel};")

    # Register and remove callback functions are from example integration - not sure if still needed
    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Button changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

class edinplus_dimmer_channel_instance:
    # Create a class for a dimmer channel (i.e. variable brightness, but no colour/temperature control)
    def __init__(self, address:int, channel: int, name: str, area: str, model: str, devcode: int, npu: edinplus_NPU_instance) -> None:
        self._dimmer_address = address
        self._channel = channel
        self._id = f"edinplus-{npu.serial_num}-{self._dimmer_address}-{self._channel}" # This ensures that automations etc aren't destroyed if the integration is removed and re-added, as dimmer channels will have the same unique id.
        self.name = name
        self.hub = npu
        self._callbacks = set()
        self._is_on = None
        # self._connected = True # This is from the original example documentation - shouldn't be needed as connection status is handled by the NPU
        self._brightness = None
        self.model = model
        self.area = area
        self._devcode = devcode

    @property
    def channel(self):
        return self._channel

    @property
    def light_id(self) -> str:
        """Return ID for light."""
        return self._id

    @property
    def is_on(self):
        return self._is_on

    @property
    def brightness(self):
        return self._brightness

    async def set_brightness(self, intensity: int):
        # Convert HomeAssistant brightness (0-255) to eDIN+ brightness (0-255)
        # NB eDIN+ uses 0-255 for brightness, same as HomeAssistant
        chan_to_scn_id = f"{str(self._dimmer_address).zfill(3)}-{str(self._channel).zfill(3)}"
        if self.hub._use_chan_to_scn_proxy and chan_to_scn_id in self.hub.chan_to_scn_proxy:
            await tcp_send_message(self.hub.writer,f"$SCNRECALLX,{self.hub.chan_to_scn_proxy[chan_to_scn_id]},{str(intensity)},{self.hub.chan_to_scn_proxy_fadetime[chan_to_scn_id]};")
            LOGGER.debug(f"[{self.hub._hostname}] Dimmer {self._dimmer_address}-{self._channel} brightness set to {intensity} via scene proxy {self.hub.chan_to_scn_proxy[chan_to_scn_id]}")
        else:
            await tcp_send_message(self.hub.writer,f"$ChanFade,{self._dimmer_address},{self._devcode},{self._channel},{str(intensity)},0;")
            LOGGER.debug(f"[{self.hub._hostname}] Dimmer {self._dimmer_address}-{self._channel} brightness set to {intensity}")
        self._is_on = (intensity > 0)
        self._brightness = intensity

    async def turn_on(self):
        # Turn on the light at full brightness
        chan_to_scn_id = f"{str(self._dimmer_address).zfill(3)}-{str(self._channel).zfill(3)}"
        if self.hub._use_chan_to_scn_proxy and chan_to_scn_id in self.hub.chan_to_scn_proxy:
            await tcp_send_message(self.hub.writer,f"$SCNRECALL,{self.hub.chan_to_scn_proxy[chan_to_scn_id]};")
            LOGGER.debug(f"[{self.hub._hostname}] Dimmer {self._dimmer_address}-{self._channel} turned on via scene proxy {self.hub.chan_to_scn_proxy[chan_to_scn_id]}")
        else:
            await tcp_send_message(self.hub.writer,f"$ChanFade,{self._dimmer_address},{self._devcode},{self._channel},255,0;")
            LOGGER.debug(f"[{self.hub._hostname}] Dimmer {self._dimmer_address}-{self._channel} turned on")
        self._is_on = True
        self._brightness = 255

    async def turn_off(self):
        # Turn off the light
        chan_to_scn_id = f"{str(self._dimmer_address).zfill(3)}-{str(self._channel).zfill(3)}"
        if self.hub._use_chan_to_scn_proxy and chan_to_scn_id in self.hub.chan_to_scn_proxy:
            await tcp_send_message(self.hub.writer,f"$SCNOFF,{self.hub.chan_to_scn_proxy[chan_to_scn_id]};")
            LOGGER.debug(f"[{self.hub._hostname}] Dimmer {self._dimmer_address}-{self._channel} turned off via scene proxy {self.hub.chan_to_scn_proxy[chan_to_scn_id]}")
        else:
            await tcp_send_message(self.hub.writer,f"$ChanFade,{self._dimmer_address},{self._devcode},{self._channel},0,0;")
            LOGGER.debug(f"[{self.hub._hostname}] Dimmer {self._dimmer_address}-{self._channel} turned off")
        self._is_on = False
        self._brightness = 0

    async def tcp_force_state_inform(self):
        # A function to force a channel to report its current status to the TCP stream
        if self.hub.writer is None or not self.hub.online:
            LOGGER.debug(f"[{self.hub._hostname}] Skipping state request for dimmer {self._dimmer_address}-{self._channel} - not connected")
            return
        LOGGER.debug(f"[{self.hub._hostname}] Requesting state for dimmer {self._dimmer_address}-{self._channel}")
        await tcp_send_message(self.hub.writer,f"?CHAN,{self._dimmer_address},{self._devcode},{self._channel};")

    # Register and remove callback functions are from example integration - not sure if still needed
    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Light changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)
