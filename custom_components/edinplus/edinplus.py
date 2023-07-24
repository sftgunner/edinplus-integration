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

LOGGER = logging.getLogger(DOMAIN)

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
        self._id = "edinpluscustomuuid-hub-"+hostname.lower()
        self._endpoint = f"http://{hostname}/gateway?1" # NB although the 1 doesn't exist in the eDIN+ API spec for gateway endpoint, it's the only way to stop requests from stripping the ? completely (which results in /gateway, a 404)
        # NB the endpoint should support alternative ports for http connection ideally (to be confirmed in config flow)
        self.lights = []
        self.manufacturer = "Mode Lighting"
        self.model = "DIN-NPU-00-01-PLUS"
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
        self.lights = await self.async_edinplus_discover_channels(config_entry)
        # Search to see if a channel has a unique scene with just it in - if so, toggle that scene rather than the channel (as keeps NPU happier!)
        self.chan_to_scn_proxy,self.chan_to_scn_proxy_fadetime = await self.async_edinplus_map_chans_to_scns()
        # Get the status for each light
        for light in self.lights:
            await light.tcp_force_state_inform()


    async def async_tcp_connect(self):
        # Create a TCP connection to the NPU
        LOGGER.debug(f"Establishing TCP connection to {self._hostname} on port {self._tcpport}")
        try:
            reader,writer = await asyncio.open_connection(self._hostname, self._tcpport)
            self.online = True
        except:
            LOGGER.error(f"Unable to establish TCP connection to eDIN+. Check hostname '{self._hostname}' and that port {self._tcpport} is open.")
            self.online = False
        if self.online:
            # Assign reader and writer objects from asyncio to the NPU class
            self.reader = reader
            self.writer = writer
            # Register to recieve all events
            await tcp_send_message(self.writer,'$EVENTS,1;')
            output = await tcp_recieve_message(self.reader)
            # Output should be !GATRDY; if all ok with the TCP connection
            if output.rstrip() == "!GATRDY;":
                LOGGER.info("TCP connection ready")
            else:
                LOGGER.warn(f"TCP connection not ready: {output}")

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
                # LOGGER.debug(f"Status of monitor task is "+{str(self.continuousTCPMonitor.done())})
                await tcp_send_message_plus(self.writer,self.reader,f"$OK;")
                try:
                    output = await asyncio.wait_for(tcp_recieve_message(self.reader), timeout=5.0)
                    if output == "":
                        self.comms_retry_attempts += 1
                        LOGGER.error(f"Failed to communicate with NPU: Empty response on port {self._tcpport}. Please check 'Gateway control' is enabled on port {self._tcpport} on the eDIN system.  Attempt {self.comms_retry_attempts}/{self.comms_max_retry_attempts} before re-establishing connection.")
                    else:
                        self.comms_retry_attempts = 0
                        LOGGER.debug(f"Acknowledge: {output}")
                except asyncio.TimeoutError:
                    self.comms_retry_attempts += 1
                    LOGGER.error(f"No acknowledgement after 5 seconds. NPU might be offline? Attempt {self.comms_retry_attempts}/{self.comms_max_retry_attempts} before re-establishing connection.")
                LOGGER.debug("Unlocking reads")
                self.readlock = False
        else:
            LOGGER.error("eDIN+ TCP connection still offline. Attempting to re-establish TCP connection.")
            await self.async_tcp_connect()
    

    async def async_response_handler(self,response):
        # Handle any messages read from the TCP stream
        if response != "":
            response_type = response.split(',')[0]
            # Parse response and determine what to do with it
            if response_type == "!INPSTATE":
                # !INPSTATE means a contact module press, meaning an event needs to be triggered with the relevant information
                # This is then processed using device_trigger.py to reassign this event (which is just JSON) to a device in the HA GUI.
                try:
                    address = int(response.split(',')[1])
                    channel = int(response.split(',')[3])
                    newstate_numeric = int(response.split(',')[4][:3])
                    newstate = NEWSTATE_TO_BUTTONEVENT[newstate_numeric]
                    uuid = f"edinpluscustomuuid-{address}-{channel}"
                    # Get the HA device ID that triggered the event 
                    device_registry = dr.async_get(self._hass)
                    device_entry = device_registry.async_get_or_create(
                        config_entry_id=self._entry_id,
                        identifiers={(DOMAIN, uuid)},
                    )

                    LOGGER.debug(f"Firing event for contact module device {uuid} with trigger type {newstate}")
                    self._hass.bus.fire(EDINPLUS_EVENT, {CONF_DEVICE_ID: device_entry.id, CONF_TYPE: newstate})
                except:
                    # This try except was a debugging step due to a small typo in an earlier version of the code - it should be safe to remove/move outside the if else clause
                    LOGGER.warning(f"An error occurred when firing event for contact module device {address}-{channel} with trigger type {newstate_numeric}")
                    LOGGER.warning(f"Full error: {response}")


            elif response_type == "!BTNSTATE":
                # !BTNSTATE means a button/keypad press, meaning an event needs to be triggered with the relevant information
                # This is then processed using device_trigger.py to reassign this event (which is just JSON) to a device in the HA GUI.
                # NB Key difference is that a keypad is presented as a single device in HA with up to 10 possible buttons, while each individual contact input is presented as its own device in HA (i.e. an 8 channel CI module would result in 8 devices), as the channels aren't necessarily in the same room
                address = int(response.split(',')[1])
                channel = int(response.split(',')[3])
                newstate_numeric = int(response.split(',')[4])
                newstate = NEWSTATE_TO_BUTTONEVENT[newstate_numeric]
                uuid = f"edinpluscustomuuid-{address}-{channel}"
                # Get the HA device ID that triggered the event 
                device_registry = dr.async_get(self._hass)
                device_entry = device_registry.async_get_or_create(
                    config_entry_id=self._entry_id,
                    identifiers={(DOMAIN, uuid)},
                )
                
                LOGGER.debug(f"Firing event for keypad module device {uuid} with trigger type {newstate}")
                self._hass.bus.fire(EDINPLUS_EVENT, {CONF_DEVICE_ID: device_entry.id, CONF_TYPE: newstate})

            elif (response_type == '!CHANFADE')or(response_type == '!CHANLEVEL'):
                LOGGER.debug(f"Chanfade/level recieved on TCP channel: {response}")
                # CHANFADE/LEVEL corresponds to a lighting channel
                for light in self.lights:
                    if light.channel == int(response.split(',')[3]):
                        light._brightness = int(response.split(',')[4])
                        LOGGER.info(f"Found light on channel {light.channel}. Writing existing brightness {light._brightness} to it in HA")
                        light._is_on = (int(response.split(',')[4]) > 0)
                        for callback in light._callbacks:
                            callback()
                        # light.update_callback()
                        
                        
            elif(response_type == '!MODULEERR'):
                # Process any errors from the eDIN+ system and pass to the HA logs
                addr = int(response.split(',')[1])
                dev = DEVCODE_TO_PRODNAME[int(response.split(',')[2])]
                statuscode = int(response.split(',')[3].split(';')[0])
                # Status code 0 = all ok!
                if statuscode != 0:
                    LOGGER.warning(f"Module error on {dev} @ address [{addr}]: {STATUSCODE_TO_SUMMARY[statuscode]} ({STATUSCODE_TO_DESC[statuscode]}")
            elif(response_type == '!CHANERR'):
                # Process any errors from the eDIN+ system and pass to the HA logs
                addr = int(response.split(',')[1])
                dev = DEVCODE_TO_PRODNAME[int(response.split(',')[2])]
                chan_num = int(response.split(',')[3])
                statuscode = int(response.split(',')[4].split(';')[0])
                if statuscode != 0:
                    LOGGER.warning(f"Module error on channel number [{chan_num}] (found on device {dev} @ address [{addr}]: {STATUSCODE_TO_SUMMARY[statuscode]} ({STATUSCODE_TO_DESC[statuscode]})")
            else:
                LOGGER.debug(f"Unknown message recieved on TCP channel: {response}")

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
        
        async_track_time_interval(hass,self.async_keep_tcp_alive, datetime.timedelta(minutes=30)) # Production
        # async_track_time_interval(hass,self.async_keep_tcp_alive, datetime.timedelta(seconds=10)) # Development


    async def async_edinplus_discover_channels(self,config_entry: ConfigEntry,):
        device_registry = dr.async_get(self._hass)
        # Add the NPU into the device registry - not required, but it makes things neater, and means the NPU shows up as a device in HA (and also appropriately shows device heirarchy)
        device_registry.async_get_or_create(
            config_entry_id = config_entry.entry_id,
            identifiers={(DOMAIN, self._id)},
            manufacturer=self.manufacturer,
            name=f"NPU ({self._name})",
            model=self.model,
        )

        # Run initial discovery using HTTP to establish what exists on the eDIN+ system linked to the NPU (returned in CSV format)
        dimmer_channel_instances = []
        NPU_raw = await async_retrieve_from_npu(f"http://{self._hostname}/info?what=names")

        NPU_data = NPU_raw.splitlines()

        areas_csv = [idx for idx in NPU_data if idx.startswith("AREA")]

        areas = {}
        channels = []
        for area in areas_csv:
            # Parsing expected format of Area,AreaNum,AreaName
            areas[int(area.split(',')[1])] = area.split(',')[2]


        plates_csv = [idx for idx in NPU_data if idx.startswith("PLATE")]

        plate_areas = {}
        plate_names = {}
        for plate in plates_csv:
            # Parsing expected format of !Plate,Address,DevCode,AreaNum,PlateName
            plate_areas[int(plate.split(',')[1])] = plate.split(',')[3]
            plate_names[int(plate.split(',')[1])] = plate.split(',')[4]

        # Lighting channels
        channels_csv = [idx for idx in NPU_data if idx.startswith("CHAN")]
        for channel in channels_csv:
            # Parsing expected format of Channel,Address,DevCode,ChanNum,AreaNum,ChanName
            channel_entity = {}
            channel_entity['address'] = int(channel.split(',')[1])
            channel_entity['channel'] = int(channel.split(',')[3])
            channel_entity['name'] = channel.split(',')[5]
            channel_entity['area'] = areas[int(channel.split(',')[4])]
            channel_entity['devcode'] = int(channel.split(',')[2])
            channel_entity['model'] = DEVCODE_TO_PRODNAME[channel_entity['devcode']]
            #print(channel_entity)
            dimmer_channel_instances.append(edinplus_dimmer_channel_instance(channel_entity['address'],channel_entity['channel'],f"{channel_entity['area']} {channel_entity['name']}",channel_entity['area'],channel_entity['model'],channel_entity['devcode'],self))

        # Contact modules
        inputs_csv = [idx for idx in NPU_data if idx.startswith("INPSTATE")]
        for input in inputs_csv:
            # Parsing expected format of Channel,Address,DevCode,ChanNum,AreaNum,ChanName
            input_entity = {}
            input_entity['address'] = int(input.split(',')[1])
            input_entity['channel'] = int(input.split(',')[3])
            input_entity['id'] = f"edinpluscustomuuid-{input_entity['address']}-{input_entity['channel']}"
            # For area on keypad this has to be matched to the PLATE
            input_entity['devcode'] = int(input.split(',')[2])
            input_entity['model'] = DEVCODE_TO_PRODNAME[input_entity['devcode']]
            if input_entity['devcode'] == 9: # Contact input module
                input_entity['name'] = input.split(',')[5]
                input_entity['area'] = areas[int(input.split(',')[4])]
                input_entity['full_name'] = f"{input_entity['area']} {input_entity['name']} switch"
            elif input_entity['devcode'] == 15: # I/O module
                input_entity['name'] = input.split(',')[5]
                input_entity['area'] = areas[int(input.split(',')[4])]
                input_entity['full_name'] = f"{input_entity['area']} {input_entity['name']} switch"
            elif input_entity['devcode'] == 2: # Wall plate
                # NB there is currently no way of telling how many buttons a wall plate has from this discovery method - this is a known issue that has been discussed with Mode Lighting
                input_entity['name'] = plate_names[int(input.split(',')[1])]
                input_entity['area'] = areas[int(plate_areas[int(input.split(',')[1])])]
                # Keypads can't have names assigned via the eDIN+ interface
                input_entity['full_name'] = f"{input_entity['area']} {input_entity['name']} button {input_entity['channel']}" # This needs to be reviewed - a keypad should only appear once, rather than having each individual button listed as a device (although this adds complexity to device_trigger as possible events need to be extended as e.g. Release-off button1, release-off button2 etc)
            else:
                # This should probably go through error handling rather than being blindly created, as it's an unknown device, and almost certainly won't work properly with the device trigger
                LOGGER.warning(f"Unknown input entity of type {DEVCODE_TO_PRODNAME[input_entity['devcode']]} found as {input_entity['name']} with id {input_entity['id']}")
                # input_entity['name'] = input.split(',')[5]
                # input_entity['area'] = areas[int(input.split(',')[4])]
                # input_entity['full_name'] = f"{input_entity['area']} {input_entity['name']} switch"
            
            LOGGER.debug(f"Input entity found {input_entity['name']} with id {input_entity['id']}")

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

        return dimmer_channel_instances
    
    
    async def async_edinplus_map_chans_to_scns_legacy(self):
        LOGGER.warning("!Using deprecated channel to scene proxy function")
        # Search for any scenes that only have a single channel, and use as a proxy for channels where possible (as this works better with mode inputs)
        # NB this needs to be improved such that only scenes with 100% brightness are used as a proxy (and only the first scene that matches - see issue open on GitHub)
        chan_to_scn_proxy = {}
        sceneList = await async_send_to_npu(self._endpoint,f"?SCNNAMES;")
        sceneIDs = []
        for sceneIdx in range(1,len(sceneList)):
            currentScene = str(sceneList[sceneIdx]).split(",")
            sceneIDs.append(currentScene[1]);
        for sceneID in sceneIDs:
            channelList = await async_send_to_npu(self._endpoint,f"?SCNCHANNAMES,{sceneID};")
            # We're searching for cases where there are only two reponses - the OK and one channel;
            if len(channelList) == 2:
                currentChannel = str(channelList[1]).split(",")
                addr = currentChannel[1]
                chan_num = currentChannel[3]
                chan_to_scn_proxy[f"{addr}-{chan_num}"] = int(sceneID)
        LOGGER.debug("Have completed channel to scene proxy mapping:")
        LOGGER.debug(chan_to_scn_proxy)
        return chan_to_scn_proxy

    async def async_edinplus_map_chans_to_scns(self):
        # An updated version of the above function, but now using the info?what=levels endpoint instead, as this ensures that scenes with a level of 0% aren't mapped
        chan_to_scn_proxy = {}
        chan_to_scn_proxy_fadetime = {}
        NPU_data = await async_retrieve_from_npu(f"http://{self._hostname}/info?what=levels")

        # !Scene,SceneNum,AreaNum,SceneName
        # !ScnFade,SceneNum,Fadetime(ms)
        # !ScnChannel,SceneNum,Address,DevCode,ChanNum,Level
        # possible_proxies = re.findall(rf"SCENE,(\d+),\d+,[\w\s]+,\d+,\d+[\s]+SCNCHANLEVEL,\d,(\d+),\d+,(\d+),255\s",NPU_data)
        possible_proxies = re.findall(rf"SCENE,(\d+),\d+,[\w\s]+SCNFADE,\d+,(\d+)[\s]+SCNCHANLEVEL,\d,(\d+),\d+,(\d+),255\s",NPU_data)
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

class edinplus_dimmer_channel_instance:
    # Create a class for a dimmer channel (i.e. variable brightness, but no colour/temperature control)
    def __init__(self, address:int, channel: int, name: str, area: str, model: str, devcode: int, npu: edinplus_NPU_instance) -> None:
        LOGGER.debug("Initialising dimmer channel instance")
        self._dimmer_address = address
        self._channel = channel
        self._id = "edinpluscustomuuid-"+str(self._dimmer_address)+"-"+str(self._channel) # This ensures that automations etc aren't destroyed if the integration is removed and re-added, as dimmer channels will have the same unique id. Not sure if there's a serial from the hardware that can be used instead (would be preferable, as the dimmer address can move if the config is changed)
        self.name = name
        self.hub = npu
        self._callbacks = set()
        self._is_on = None
        self._connected = True # This is from the original example documentation - shouldn't be needed as connection status is handled by the NPU
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
            # LOGGER.debug(f"Expected: {expectedResponse}")
            # if expectedResponse in self.hub.queuedresponses:
            #     self.hub.queuedresponses.remove(expectedResponse) #Remove queued response
            #     LOGGER.debug(f"Acknowlegement recieved")
            # else:
            #     LOGGER.warning(f"No acknowlegement recieved. Expected {expectedResponse}. Current queue:")
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
        LOGGER.debug(f"?CHAN,{self._dimmer_address},{self._devcode},{self._channel};")
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
