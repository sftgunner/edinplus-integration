"""Python library to enable communication with eDIN+ for the HomeAssistant integration."""

# To be considered for an official HomeAssistant integration, this will need to be separated from the rest of the integration and setup as a pypi library.
# NB: This is currently not possible due to the dependency on async_track_time_interval

from __future__ import annotations
import asyncio
import requests
import logging
import time
import aiohttp
import datetime
import re

from homeassistant.core import HomeAssistant

from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import device_registry as dr
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_TOKEN,
    CONF_TYPE,
)

# Import constants
from .const import *

LOGGER = logging.getLogger(__name__)

# Interact with NPU using the TCP stream (the writer object should be stored in the NPU class)
async def tcp_send_message(writer,message):
    LOGGER.debug(f'TCP TX: {message!r}')
    writer.write(message.encode())
    await writer.drain()
    
# Read messages from the NPU using the TCP stream (the reader object should be stored in the NPU class)
async def tcp_recieve_message(reader):
    # if not reader.at_eof():
    data = await reader.readline()
    return data.decode()

# Async method of interrogating NPU via HTTP. 
# Used for discovery only
async def async_retrieve_from_npu(endpoint):
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint) as resp:
            response = await resp.text()
    return response

# Old TCP test function to try and write to TCP stream and immediately read acknowledgement (to verify change had been written correctly)
# Unfortunately didn't work due to conflicts with existing pending tcp_receive_message
async def tcp_send_message_plus(writer,reader,message):
    LOGGER.debug(f'Sending_plus: {message!r}')
    writer.write(message.encode())
    await writer.drain()
    # try:
    #     async with asyncio.timeout(10):
    #         data = await reader.readline()
    #         LOGGER.debug(f'Acknowledgement: {data.decode()!r}')
    #         # return data.decode()
    # except TimeoutError:
    #     print("ERR! Looks like NPU is offline: took more than 10 seconds to get a response.")
    # self.readlock = False

# Async method of interrogating NPU via HTTP. 
# !! This should be deprecated in favour of tcp_send_message above
async def async_send_to_npu(endpoint,data):
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint,data=data) as resp:
            response = await resp.text()
    return response.splitlines()

# Old synchronous function to post data to the NPU via HTTP (should now be unused, for reference only)
def send_to_npu(endpoint,data):
    response = requests.post(endpoint, data = data)
    return response.content.decode("utf-8").splitlines()

class edinplus_NPU_instance:
    def __init__(self,hass: HomeAssistant,hostname:str,entry_id) -> None:
        LOGGER.debug("Initialising NPU")
        self._hostname = hostname
        self._hass = hass
        self._name = hostname
        self._tcpport = 26 # This should be configurable using the config flow (as it's possible to change on the NPU)
        self._entry_id = entry_id
        self._id = f"edinplus-hub-{hostname.lower()}"
        self._endpoint = f"http://{hostname}/gateway?1" # NB although the 1 doesn't exist in the eDIN+ API spec for gateway endpoint, it's the only way to stop requests from stripping the ? completely (which results in /gateway, a 404)
        # NB the endpoint should support alternative ports for http connection ideally (to be confirmed in config flow)
        self.lights = []
        self.switches = []
        self.buttons = []
        self.binary_sensors = []
        self.manufacturer = "Mode Lighting"
        self.model = "DIN-NPU-00-01-PLUS"
        self.serial = None
        self.reader = None
        self.writer = None
        self.continuousTCPMonitor = None # For the coroutine task that monitors the TCP stream
        self.readlock = False
        self._callbacks = set()
        self._use_chan_to_scn_proxy = True # This should be offered in config flow (although not sure why you would ever not want it)
        self.chan_to_scn_proxy = {}
        self.chan_to_scn_proxy_fadetime = {}
        self.online = False
        self.comms_retry_attempts = 0 
        self.comms_max_retry_attempts = 5 # The number of retries before we try and re-establish the TCP connection
        LOGGER.debug("Initialised NPU instance (in edinplus.py)")
    
    async def discover(self,config_entry: ConfigEntry):
        # Discover all lighting channels on devices connected to NPU
        self.lights,self.switches,self.buttons,self.binary_sensors = await self.async_edinplus_discover_channels(config_entry)
        # Search to see if a channel has a unique scene with just it in - if so, toggle that scene rather than the channel (as keeps NPU happier!)
        self.chan_to_scn_proxy,self.chan_to_scn_proxy_fadetime = await self.async_edinplus_map_chans_to_scns()
        # Get the status for each light
        for light in self.lights:
            await light.tcp_force_state_inform()
        # Get the status for each switch
        for switch in self.switches:
            await switch.tcp_force_state_inform()
        # Get the status for each binary sensor
        for binary_sensor in self.binary_sensors:
            await binary_sensor.tcp_force_state_inform()


    async def async_tcp_connect(self):
        # Create a TCP connection to the NPU
        LOGGER.debug(f"[{self._hostname}] Establishing TCP connection to {self._hostname} on port {self._tcpport}")
        try:
            reader,writer = await asyncio.open_connection(self._hostname, self._tcpport)
            self.online = True
        except:
            LOGGER.error(f"[{self._hostname}] Unable to establish TCP connection to eDIN+ NPU. Check hostname '{self._hostname}' and that port {self._tcpport} is open.")
            self.online = False
        if self.online:
            # Assign reader and writer objects from asyncio to the NPU class
            self.reader = reader
            self.writer = writer
            # Register to recieve all events
            await tcp_send_message(self.writer,'$EVENTS,1;')
            output = await tcp_recieve_message(self.reader)
            # Output should be !GATRDY; if all ok with the TCP connection

            if output.rstrip() == "":
                LOGGER.error(f"[{self._hostname}] eDIN+ integration not getting any TCP response from the NPU.")
                LOGGER.error(f"[{self._hostname}] Try rebooting the NPU (Configuration -> Tools -> Reinitialise system -> Reboot system) and then reload the integration in HomeAssistant")
            elif output.rstrip() == "!GATRDY;":
                LOGGER.info("TCP connection ready")
            else:
                LOGGER.error(f"[{self._hostname}] TCP connection not ready; received message: {output}")

    async def async_keep_tcp_alive(self,now=None):
        # This serves two purposes - to keep the connection alive and also to check that it hasn't been terminated at the other end
        # NPU will terminate TCP connection if no activity for an hour (to verify)
        # In future, could be more useful to use this function to check that the NPU configuration hasn't changed (and if it has, to re-run discover to find the added/removed devices)
        
        # NB the communication logic seems to be a bit flaky, due to asyncio reader not timing out correctly (i.e. it's still waiting for addtional bytes when in fact the connection has closed). This also has potential to overload the NPU if connection not properly terminated
        if self.online:
            if self.comms_retry_attempts >= self.comms_max_retry_attempts:
                LOGGER.error("Max retries on TCP connection reached. Attempting to re-establish TCP connection")
                self.comms_retry_attempts = 0
                await self.async_tcp_connect()
            else:
                LOGGER.debug("Keeping TCP connection alive")
                self.readlock = True
                LOGGER.debug("Locking reads and cancelling continuous task")
                # NB This cancellation isn't reliable at the moment)
                self.continuousTCPMonitor.cancel()
                # LOGGER.debug(f"[{self._hostname}] Status of monitor task is "+{str(self.continuousTCPMonitor.done())})
                # await tcp_send_message_plus(self.writer,self.reader,f"$OK;")
                await tcp_send_message(self.writer,"$OK;")
                try:
                    output = await asyncio.wait_for(tcp_recieve_message(self.reader), timeout=5.0)
                    if output == "":
                        self.comms_retry_attempts += 1
                        LOGGER.error(f"[{self._hostname}] Failed to communicate with NPU: Empty response on port {self._tcpport}. Please check 'Gateway control' is enabled on port {self._tcpport} on the eDIN system.  Attempt {self.comms_retry_attempts}/{self.comms_max_retry_attempts} before re-establishing connection.")
                    else:
                        self.comms_retry_attempts = 0
                        LOGGER.debug(f"[{self._hostname}] Acknowledge: {output}")
                except asyncio.TimeoutError:
                    self.comms_retry_attempts += 1
                    LOGGER.error(f"[{self._hostname}] No acknowledgement after 5 seconds. NPU might be offline? Attempt {self.comms_retry_attempts}/{self.comms_max_retry_attempts} before re-establishing connection.")
                except RuntimeError: # Catch the runtime error "RuntimeError: readuntil() called while another coroutine is already waiting for incoming data" to avoid readlock getting stuck in True
                    LOGGER.warning(f"[{self._hostname}] Caught Runtime error")
                LOGGER.debug("Unlocking reads")
                self.readlock = False
        else:
            LOGGER.error("eDIN+ TCP connection still offline. Attempting to re-establish TCP connection.")
            await self.async_tcp_connect()
    

    async def async_response_handler(self,response):
        # Handle any messages read from the TCP stream
        if response != "":
            LOGGER.debug(f"[{self._hostname}] {response}")
            response_type = response.split(',')[0]
            # Parse response and determine what to do with it
            if response_type == "!INPSTATE":
                # !INPSTATE means a contact module press, meaning an event needs to be triggered with the relevant information
                # This is then processed using device_trigger.py to reassign this event (which is just JSON) to a device in the HA GUI.
                # try:
                address = int(response.split(',')[1])
                channel = int(response.split(',')[3])
                newstate_numeric = int(response.split(',')[4][:3])
                newstate = NEWSTATE_TO_BUTTONEVENT[newstate_numeric]
                uuid = f"edinplus-{self.serial}-{address}-{channel}"
                # Get the HA device ID that triggered the event 
                device_registry = dr.async_get(self._hass)

                LOGGER.debug(f"[{self._hostname}] 211 Creating or getting device in registry with no name and id {uuid}")
                device_entry = device_registry.async_get_or_create(
                    config_entry_id=self._entry_id,
                    identifiers={(DOMAIN, uuid)},
                )
                found_binary_sensor_channel = False
                for binary_sensor in self.binary_sensors:
                    if binary_sensor.channel == channel and binary_sensor._address == address:
                        found_binary_sensor_channel = True
                        LOGGER.info(f"[{self._hostname}] Found binary sensor corresponding to address {binary_sensor._address}, channel {binary_sensor.channel} in HA. Writing state {newstate_numeric > 0}")
                        if (binary_sensor._is_on == None):
                            binary_sensor_discovery_in_progress = True
                        else:
                            binary_sensor_discovery_in_progress = False
                        
                        binary_sensor._is_on = (newstate_numeric > 0)
                        for callback in binary_sensor._callbacks:
                            callback()
                if (found_binary_sensor_channel == False):
                    LOGGER.warning(f"[{self._hostname}] Binary sensor without corresponding entity found; address {binary_sensor._address}, channel {binary_sensor.channel}")
                    binary_sensor_discovery_in_progress = False

                if (binary_sensor_discovery_in_progress):
                    LOGGER.debug(f"[{self._hostname}] NOT Firing event for contact module device {uuid} with trigger type {newstate} as discovery active")
                else:
                    LOGGER.debug(f"[{self._hostname}] Firing event for contact module device {uuid} with trigger type {newstate}")
                    self._hass.bus.fire(EDINPLUS_EVENT, {CONF_DEVICE_ID: device_entry.id, CONF_TYPE: newstate})
                # except:
                #     # This try except was a debugging step due to a small typo in an earlier version of the code - it should be safe to remove/move outside the if else clause
                #     LOGGER.warning(f"[{self._hostname}] An error occurred when firing event for contact module device {address}-{channel} with trigger type {newstate_numeric}")
                #     LOGGER.warning(f"[{self._hostname}] Full error: {response}")


            elif response_type == "!BTNSTATE":
                # !BTNSTATE means a button/keypad press, meaning an event needs to be triggered with the relevant information
                # This is then processed using device_trigger.py to reassign this event (which is just JSON) to a device in the HA GUI.
                # NB Key difference is that a keypad is presented as a single device in HA with up to 10 possible buttons, while each individual contact input is presented as its own device in HA (i.e. an 8 channel CI module would result in 8 devices), as the channels aren't necessarily in the same room
                address = int(response.split(',')[1])
                channel = int(response.split(',')[3])

                # NB need to exclude channel in place of whole keypad
                newstate_numeric = int(response.split(',')[4][:3])
                newstate = f"Button {channel} {NEWSTATE_TO_BUTTONEVENT[newstate_numeric]}"
                uuid = f"edinplus-{self.serial}-{address}-1" # Channel is always 1 in the UUID for a keypad due to the way that the NPU presents keypads
                # Get the HA device ID that triggered the event 
                device_registry = dr.async_get(self._hass)

                self._id

                LOGGER.debug(f"[{self._hostname}] 243 Creating or getting device in registry with no name and id {uuid}")
                device_entry = device_registry.async_get_or_create(
                    config_entry_id=self._entry_id,
                    identifiers={(DOMAIN, uuid)},
                )
                
                LOGGER.debug(f"[{self._hostname}] Firing event for keypad module device {uuid} with trigger type {newstate}")
                self._hass.bus.fire(EDINPLUS_EVENT, {CONF_DEVICE_ID: device_entry.id, CONF_TYPE: newstate})

            elif (response_type == '!CHANFADE')or(response_type == '!CHANLEVEL'):
                LOGGER.debug(f"[{self._hostname}] Chanfade/level recieved on TCP channel: {response}")
                # CHANFADE/LEVEL corresponds to a lighting channel
                for light in self.lights:
                    if light.channel == int(response.split(',')[3]) and light._dimmer_address == int(response.split(',')[1]):
                        LOGGER.info(f"[{self._hostname}] Found light corresponding to address {light._dimmer_address}, channel {light.channel} in HA. Writing observed brightness {light._brightness}")
                        light._is_on = (int(response.split(',')[4]) > 0)
                        light._brightness = int(response.split(',')[4])

                        for callback in light._callbacks:
                            callback()
                for switch in self.switches:
                    if switch.channel == int(response.split(',')[3]) and switch._address == int(response.split(',')[1]):
                        LOGGER.info(f"[{self._hostname}] Found switch corresponding to address {switch._address}, channel {switch.channel} in HA. Writing state {(int(response.split(',')[4]) > 0)}")
                        switch._is_on = (int(response.split(',')[4]) > 0)

                        for callback in switch._callbacks:
                            callback()
                        # light.update_callback()
                        
                        
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
                LOGGER.debug(f"[{self._hostname}] NPU acknowledgement: {response}")
            elif(response_type == '!SCNOFF'):
                LOGGER.debug(f"[{self._hostname}] NPU confirmed scene {response.split(',')[1].split(';')[0]} is now off")
            elif(response_type == '!SCNRECALL'):
                LOGGER.debug(f"[{self._hostname}] NPU confirmed scene {response.split(',')[1].split(';')[0]} has been recalled (i.e. is on)")
            elif(response_type == '!SCNSTATE'):
                LOGGER.debug(f"[{self._hostname}] NPU confirmed scene {response.split(',')[1]} has been set to {round(int(response.split(',')[3])/2.55)}% of max scene brightness")
            else:
                LOGGER.debug(f"[{self._hostname}] !UNKNOWN TCP RX: {response}")

    async def async_monitor_tcp(self,now=None):
        # This is the function that keeps track of any new messages on the TCP stream, triggered every 0.01s by the function monitor below
        if self.online:
            if self.readlock:
                # Unable to read as reading already in progress (as this is scheduled for every 0.01s, most of the time no new data will have arrived, so the previous async_monitor_tcp will still be waiting for an EOF)
                pass
            else:
                # Set readlock to ensure that we don't have multiple functions trying to read from the stream simultaneously
                self.readlock = True
                # In theory if you run tcp_recieve_message as a task, it can then be cancelled, but this doesn't seem to be reliable
                self.continuousTCPMonitor = asyncio.create_task(tcp_recieve_message(self.reader))
                response = await self.continuousTCPMonitor
                await self.async_response_handler(response)
                # Unlock reads - if the continuousTCPMonitor has finished, then an EOF has been reached, so this function needs to be re-run
                self.readlock = False
            

    async def monitor(self, hass: HomeAssistant) -> None:
        # As discussed above, try and monitor the TCP stream every 0.01s - this will nearly always immediately end, assuming there is already an existing instance of the function waiting for an EOF
        async_track_time_interval(hass,self.async_monitor_tcp, datetime.timedelta(seconds=0.01))
        
        # For production, ideally only keep tcp alive every half hour (as NPU will terminate TCP stream if no activity for 60 minutes)
        # However, for debugging/development, this has been set to every 10 seconds (especially useful for trying to test the ability of the integration to recover when the NPU goes offline and then later online.
        
        async_track_time_interval(hass,self.async_keep_tcp_alive, datetime.timedelta(minutes=10)) # Production
        # async_track_time_interval(hass,self.async_keep_tcp_alive, datetime.timedelta(seconds=10)) # Development


    async def async_edinplus_discover_channels(self,config_entry: ConfigEntry,):
        device_registry = dr.async_get(self._hass)
        # Add the NPU into the device registry - not required, but it makes things neater, and means the NPU shows up as a device in HA (and also appropriately shows device hierarchy)
        LOGGER.debug(f"[{self._hostname}] 325 Creating device in registry with name NPU ({self._name}) and id {self._id}")
        device_registry.async_get_or_create(
            config_entry_id = config_entry.entry_id,
            identifiers={(DOMAIN, self._id)},
            manufacturer=self.manufacturer,
            name=f"NPU ({self._name})",
            model=self.model,
            configuration_url=f"http://{self._hostname}",
        )

        # Run initial discovery using HTTP to establish what exists on the eDIN+ system linked to the NPU (returned in CSV format)
        dimmer_channel_instances = []
        relay_channel_instances = []
        relay_pulse_instances = []
        binary_sensor_instances = []

        NPU_raw = await async_retrieve_from_npu(f"http://{self._hostname}/info?what=names")

        # Determine NPU serial number
        try:
            serial_number = re.findall(r"!SYSTEMID,(\d{4})",NPU_raw)
            self.serial = serial_number[0]
            LOGGER.debug(f"[{self._hostname}] Serial number of NPU assigned as {self.serial}")
        except:
            LOGGER.error("Could not find serial number of the eDIN+ system. Please report this issue to the developer of the integration.")

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
        for input in inputs_csv:
            # Parsing expected format of Channel,Address,DevCode,ChanNum,AreaNum,ChanName
            input_entity = {}
            input_entity['address'] = int(input.split(',')[1])
            input_entity['channel'] = int(input.split(',')[3])
            input_entity['id'] = f"edinplus-{self.serial}-{input_entity['address']}-{input_entity['channel']}"
            # For area on keypad this has to be matched to the PLATE
            input_entity['devcode'] = int(input.split(',')[2])
            input_entity['model'] = DEVCODE_TO_PRODNAME[input_entity['devcode']]
            if input_entity['devcode'] in [9,15]: # Contact input module, I/O module
                input_entity['name'] = input.split(',')[5]
                if not input_entity['name']:
                    input_entity['name'] = f"Unnamed {input_entity['model']} addr {input_entity['address']} chan {input_entity['channel']}"
                input_entity['area'] = areas[int(input.split(',')[4])]
                input_entity['full_name'] = f"{input_entity['area']} {input_entity['name']}"
                binary_sensor_instances.append(edinplus_input_binary_sensor_instance(input_entity['address'],input_entity['channel'],f"{input_entity['area']} {input_entity['name']}",input_entity['area'],input_entity['model'],input_entity['devcode'],self))
            elif input_entity['devcode'] in [1,2]: # Wall plate
                # NB there is currently no way of telling how many buttons a wall plate has from this discovery method - this is a known issue that has been discussed with Mode Lighting
                # Consequently we only store this once for "channel 1" - in reality the CSV file has channel 1 and 2, irrespective of how many buttons there actually are on the keypad
                if input_entity['channel'] != 1:
                    continue
                # The name also has to be matched to the PLATE name if it exists (else do unnamed wall plate address #)
                plate_info = re.findall(rf"PLATE,{input_entity['address']},2,(\d+),([\w ]+)?",NPU_raw)
                plate_name = plate_info[0][1] 
                plate_area = areas[int(plate_info[0][0])]
                if not plate_name:
                    plate_name = f"Unnamed Wall Plate address {input_entity['address']}"

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
            
            LOGGER.debug(f"[{self._hostname}] Input entity found: {input_entity['model']} '{input_entity['name']}' (id: {input_entity['id']})")

            LOGGER.debug(f"[{self._hostname}] Creating device in registry: {input_entity['full_name']} ({input_entity['id']})")

            device_registry.async_get_or_create(
                config_entry_id = config_entry.entry_id,
                identifiers={(DOMAIN, input_entity['id'])},
                manufacturer=self.manufacturer,
                # name=f"Light switch ({input_entity['name']})",
                name=input_entity['full_name'],
                suggested_area=input_entity['area'],
                model=input_entity['model'],
                via_device=(DOMAIN,self._id),
            )

        return dimmer_channel_instances,relay_channel_instances,relay_pulse_instances,binary_sensor_instances

    async def async_edinplus_map_chans_to_scns(self):
        # Search for any scenes that only have a single channel, and use as a proxy for channels where possible (as this works better with mode inputs)
        # Now using the info?what=levels endpoint instead, as this ensures that scenes with a level of 0% aren't mapped
        chan_to_scn_proxy = {}
        chan_to_scn_proxy_fadetime = {}
        NPU_data = await async_retrieve_from_npu(f"http://{self._hostname}/info?what=levels")

        # !Scene,SceneNum,AreaNum,SceneName
        # !ScnFade,SceneNum,Fadetime(ms)
        # !ScnChannel,SceneNum,Address,DevCode,ChanNum,Level
        # possible_proxies = re.findall(rf"SCENE,(\d+),\d+,[\w\s]+,\d+,\d+[\s]+SCNCHANLEVEL,\d,(\d+),\d+,(\d+),255\s",NPU_data)
        possible_proxies = re.findall(rf"SCENE,(\d+),\d+,[\w\s]+SCNFADE,\d+,(\d+)[\s]+SCNCHANLEVEL,\d+,(\d+),\d+,(\d+),255\s\s",NPU_data)
        # Will return all possible proxies in sequence: Scene number, FadeTime, Address, ChanNum

        for proxy_combo in possible_proxies:
            sceneID = proxy_combo[0]
            fadeTime = proxy_combo[1]
            addr = proxy_combo[2].zfill(3)
            chan_num = proxy_combo[3].zfill(3)

            chan_to_scn_proxy[f"{addr}-{chan_num}"] = int(sceneID)
            chan_to_scn_proxy_fadetime[f"{addr}-{chan_num}"] = int(fadeTime)

        LOGGER.debug("Have completed channel to scene proxy mapping (using v2):")
        LOGGER.debug(chan_to_scn_proxy)
        LOGGER.debug("Have also found default fadetimes for scene proxy mapping:")
        LOGGER.debug(chan_to_scn_proxy_fadetime)
        return chan_to_scn_proxy,chan_to_scn_proxy_fadetime

class edinplus_relay_channel_instance:
    def __init__(self, address:int, channel: int, name: str, area: str, model: str, devcode: int, npu: edinplus_NPU_instance) -> None:
        self._address = address
        self._channel = channel
        self._id = f"edinplus-{npu.serial}-{self._address}-{self._channel}" # This ensures that automations etc aren't destroyed if the integration is removed and re-added, as channels will have the same unique id.
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

    async def turn_off(self):
        await tcp_send_message(self.hub.writer,f"$ChanFade,{self._address},{self._devcode},{self._channel},0,0;")
        self._is_on = False

    async def tcp_force_state_inform(self):
        # A function to force a channel to report its current status to the TCP stream
        LOGGER.debug(f"[{self.hub._hostname}] Forcing state inform for address-channel: {self._address},{self._channel}")
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
        self._id = f"edinplus-{npu.serial}-{self._address}-{self._channel}" # This ensures that automations etc aren't destroyed if the integration is removed and re-added, as channels will have the same unique id.
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
        self._id = f"edinplus-{npu.serial}-{self._address}-{self._channel}" # This ensures that automations etc aren't destroyed if the integration is removed and re-added, as channels will have the same unique id.
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
        LOGGER.debug(f"[{self.hub._hostname}] Forcing state inform for address-channel: {self._address},{self._channel}")
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
        self._id = f"edinplus-{npu.serial}-{self._dimmer_address}-{self._channel}" # This ensures that automations etc aren't destroyed if the integration is removed and re-added, as dimmer channels will have the same unique id.
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
        chan_to_scn_id = f"{str(self._dimmer_address).zfill(3)}-{str(self._channel).zfill(3)}"
        if self.hub._use_chan_to_scn_proxy and chan_to_scn_id in self.hub.chan_to_scn_proxy:
            await tcp_send_message(self.hub.writer,f"$SCNRECALLX,{self.hub.chan_to_scn_proxy[chan_to_scn_id]},{str(intensity)},{self.hub.chan_to_scn_proxy_fadetime[chan_to_scn_id]};")
        else:
            await tcp_send_message(self.hub.writer,f"$ChanFade,{self._dimmer_address},{self._devcode},{self._channel},{str(intensity)},0;")
        self._brightness = intensity

    async def turn_on(self):
        chan_to_scn_id = f"{str(self._dimmer_address).zfill(3)}-{str(self._channel).zfill(3)}"
        if self.hub._use_chan_to_scn_proxy and chan_to_scn_id in self.hub.chan_to_scn_proxy:
            await tcp_send_message(self.hub.writer,f"$SCNRECALL,{self.hub.chan_to_scn_proxy[chan_to_scn_id]};")
            # Code below was an attempt to verify changes had been written correctly, but due to async nature, doesn't seem to work - further investigation required
            expectedResponse = f"!OK,SCNRECALL,{self.hub.chan_to_scn_proxy[chan_to_scn_id]:05d};"
            # time.sleep(0.02)
            # LOGGER.debug(f"[{self.hub._hostname}] Expected: {expectedResponse}")
            # if expectedResponse in self.hub.queuedresponses:
            #     self.hub.queuedresponses.remove(expectedResponse) #Remove queued response
            #     LOGGER.debug(f"[{self.hub._hostname}] Acknowlegement recieved")
            # else:
            #     LOGGER.warning(f"[{self.hub._hostname}] No acknowlegement recieved. Expected {expectedResponse}. Current queue:")
            #     LOGGER.warning(self.hub.queuedresponses)
        else:
            await tcp_send_message(self.hub.writer,f"$ChanFade,{self._dimmer_address},{self._devcode},{self._channel},255,0;")
        self._is_on = True

    async def turn_off(self):
        chan_to_scn_id = f"{str(self._dimmer_address).zfill(3)}-{str(self._channel).zfill(3)}"
        if self.hub._use_chan_to_scn_proxy and chan_to_scn_id in self.hub.chan_to_scn_proxy:
            await tcp_send_message(self.hub.writer,f"$SCNOFF,{self.hub.chan_to_scn_proxy[chan_to_scn_id]};")
        else:
            await tcp_send_message(self.hub.writer,f"$ChanFade,{self._dimmer_address},{self._devcode},{self._channel},0,0;")
        self._is_on = False

    async def tcp_force_state_inform(self):
        # A function to force a channel to report its current status to the TCP stream
        # LOGGER.debug(f"[{self.hub._hostname}] ?CHAN,{self._dimmer_address},{self._devcode},{self._channel};")
        LOGGER.debug(f"[{self.hub._hostname}] Forcing state inform for address-channel: {self._dimmer_address},{self._channel}")
        await tcp_send_message(self.hub.writer,f"?CHAN,{self._dimmer_address},{self._devcode},{self._channel};")
    
    async def get_brightness(self):
        LOGGER.warning("Polling using HTTP endpoint")
        # !! Usage of async_send_to_npu should be deprecated in favour of tcp_send_message
        output = await async_send_to_npu(self.hub._endpoint,f"?CHAN,{self._dimmer_address},{self._devcode},{self._channel};")
        # Relevant response is in third line starting CHANLEVEL
        # Will be in second line if attempting to call a non existent channel
        brightness = output[2].split(',')[4]
        return brightness

# Register and remove callback functions are from example integration - not sure if still needed
    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Light changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)
