from __future__ import annotations
import asyncio
import requests
import logging

from homeassistant.core import HomeAssistant

import aiohttp
import datetime

from homeassistant.helpers.event import async_track_time_interval

# Import constants
from .const import *

LOGGER = logging.getLogger(__name__)


def send_to_npu(endpoint,data):
    response = requests.post(endpoint, data = data)
    return response.content.decode("utf-8").splitlines()


async def async_send_to_npu(endpoint,data):
    async with aiohttp.ClientSession() as session:
        async with session.post(endpoint,data=data) as resp:
            #print(resp.status)
            response = await resp.text()

    #response = requests.post(endpoint, data = data)
    #return response.content.decode("utf-8").splitlines()
    return response.splitlines()

async def async_retrieve_from_npu(endpoint):
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint) as resp:
            response = await resp.text()
    return response.splitlines()

async def tcp_send_message(writer,message):
    # print(f'Send: {message!r}')
    writer.write(message.encode())
    await writer.drain()

async def tcp_recieve_message(reader):
    data = await reader.readline()
    #print(f'Received: {data.decode()!r}')
    return data.decode()

class edinplus_NPU_instance:
    def __init__(self,hass: HomeAssistant,hostname:str) -> None:
        LOGGER.debug("Initialising NPU")
        self._hostname = hostname
        self._hass = hass
        self._name = hostname
        self._id = "edinpluscustomuuid-hub-"+hostname.lower()
        #NB although the 1 doesn't exist in the Edin+ API spec for gateway endpoint, it's the only way to stop requests from stripping it completely (which results in /gateway, a 404)
        self._endpoint = f"http://{hostname}/gateway?1"
        self.lights = []
        self.manufacturer = "Mode Lighting"
        self.reader = None
        self.writer = None
        self.readlock = False
        self._callbacks = set()
        # This should be offered in config flow
        self._use_chan_to_scn_proxy = True
        self.chan_to_scn_proxy = {}
        LOGGER.debug("Initialised NPU instance (in edinplus.py)")
    
    async def discover(self):
        self.lights = await self.async_edinplus_discover_channels()
        # Get the status for each light
        for light in self.lights:
            await light.tcp_force_state_inform()

        self.chan_to_scn_proxy = await self.async_edinplus_map_chans_to_scns()

    async def async_tcp_connect(self):
        reader, writer = await asyncio.open_connection(self._hostname, 26)
        self.reader = reader
        self.writer = writer
        # Register to recieve all events
        await tcp_send_message(self.writer,'$EVENTS,1;')
        output = await tcp_recieve_message(self.reader)
        # Output should be !GATRDY;
        if output == "!GATRDY;":
            LOGGER.info("TCP connection ready")
        else:
            LOGGER.warn(f"TCP connection not ready: {output}")    

    async def async_keep_tcp_alive(self,now=None):
        LOGGER.debug("Keeping TCP connection alive")
        await tcp_send_message(self.writer,f"$OK;")
    

    async def async_response_handler(self,response):
        if response != "":
            response_type = response.split(',')[0]
            # Parse response and determine what to do with it
            if response_type == "!INPSTATE":
                #It's a contact module press - fire a custom event!
                edinplus_event = {}
                edinplus_event['address'] = int(response.split(',')[1])
                edinplus_event['device'] = DEVCODE_TO_PRODNAME[int(response.split(',')[2])]
                edinplus_event['channel'] = int(response.split(',')[3])
                edinplus_event['newstate'] = int(response.split(',')[4].split(';')[0])
                edinplus_event['newstate_desc'] = NEWSTATE_TO_BUTTONEVENT[edinplus_event['newstate']]
                edinplus_event['description'] = "Change in switched input"
                edinplus_event['raw'] = response
                LOGGER.info(f"Firing contact module press event: {edinplus_event}")
                self._hass.bus.fire("edinplus_event", edinplus_event)
            elif response_type == "!BTNSTATE":
                #It's a keypad module press - fire a custom event!
                edinplus_event = {}
                edinplus_event['address'] = int(response.split(',')[1])
                edinplus_event['device'] = DEVCODE_TO_PRODNAME[int(response.split(',')[2])]
                edinplus_event['channel'] = int(response.split(',')[3])
                edinplus_event['newstate'] = int(response.split(',')[4].split(';')[0])
                edinplus_event['newstate_desc'] = NEWSTATE_TO_BUTTONEVENT[edinplus_event['newstate']]
                edinplus_event['description'] = "Change in button switch state"
                edinplus_event['raw'] = response
                LOGGER.info(f"Firing keypad module press event: {edinplus_event}")
                self._hass.bus.fire("edinplus_event", edinplus_event)
            elif (response_type == '!CHANFADE')or(response_type == '!CHANLEVEL'):
                for light in self.lights:
                    if light.channel == int(response.split(',')[3]):
                        light._brightness = int(response.split(',')[4])
                        LOGGER.info(f"Found light on channel {light.channel}. Writing brightness {light._brightness} to it")
                        light._is_on = (int(response.split(',')[4]) > 0)
                        for callback in light._callbacks:
                            callback()
                        # light.update_callback()
            elif(response_type == '!MODULEERR'):
                addr = int(response.split(',')[1])
                dev = DEVCODE_TO_PRODNAME[int(response.split(',')[2])]
                statuscode = int(response.split(',')[3].split(';')[0])
                # Status code 0 = all ok!
                if statuscode != 0:
                    LOGGER.warning(f"Module error on {dev} @ address [{addr}]: {STATUSCODE_TO_SUMMARY[statuscode]} ({STATUSCODE_TO_DESC[statuscode]}")
            elif(response_type == '!CHANERR'):
                addr = int(response.split(',')[1])
                dev = DEVCODE_TO_PRODNAME[int(response.split(',')[2])]
                chan_num = int(response.split(',')[3])
                statuscode = int(response.split(',')[4].split(';')[0])
                if statuscode != 0:
                    LOGGER.warning(f"Module error on channel number [{chan_num}] (found on device {dev} @ address [{addr}]: {STATUSCODE_TO_SUMMARY[statuscode]} ({STATUSCODE_TO_DESC[statuscode]})")
            else:
                LOGGER.debug(f"Unknown message recieved on TCP channel: {response}")
        else:
            LOGGER.debug("TCP rx: Empty response")

    async def async_monitor_tcp(self,now=None):
        if self.readlock:
            # LOGGER.debug("Unable to read as reading already in progress")
            pass
        else:
            # LOGGER.warning("Monitoring")
            self.readlock = True
            response = await tcp_recieve_message(self.reader)
            self.readlock = False
            await self.async_response_handler(response)
            

    async def monitor(self, hass: HomeAssistant) -> None:
        async_track_time_interval(hass,self.async_monitor_tcp, datetime.timedelta(seconds=0.01))
        async_track_time_interval(hass,self.async_keep_tcp_alive, datetime.timedelta(minutes=30))


    async def async_edinplus_discover_channels(self):
        dimmer_channel_instances = []
        NPU_data = await async_retrieve_from_npu(f"http://{self._hostname}/info?what=names")

        areas_csv = [idx for idx in NPU_data if idx.startswith("AREA")]

        areas = {}
        channels = []
        for area in areas_csv:
            # Parsing expected format of Area,AreaNum,AreaName
            areas[int(area.split(',')[1])] = area.split(',')[2]

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

        inputs_csv = [idx for idx in NPU_data if idx.startswith("INPSTATE")]
        for input in inputs_csv:
            # Parsing expected format of Channel,Address,DevCode,ChanNum,AreaNum,ChanName
            input_entity = {}
            input_entity['address'] = int(input.split(',')[1])
            input_entity['channel'] = int(input.split(',')[3])
            input_entity['name'] = input.split(',')[5]
            input_entity['area'] = areas[int(input.split(',')[4])]
            input_entity['devcode'] = int(input.split(',')[2])
            input_entity['model'] = DEVCODE_TO_PRODNAME[input_entity['devcode']]
            LOGGER.info(f"Have found input entity {input_entity['name']} in room {input_entity['area']} but support for inputs has not been added yet.")
            # INPUT ENTITIES CURRENTLY DISABLED
            #print(input_entity)
            #dimmer_channel_instances.append(edinplus_dimmer_channel_instance(channel_entity['address'],channel_entity['channel'],channel_entity['name'],channel_entity['area'],channel_entity['model'],self))

        return dimmer_channel_instances
    async def async_edinplus_map_chans_to_scns(self):
        # Search for any scenes that only have a single channel, and use as a proxy for channels where possible (as this works better with mode inputs)
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

class edinplus_dimmer_channel_instance:
    def __init__(self, address:int, channel: int, name: str, area: str, model: str, devcode: int, npu: edinplus_NPU_instance) -> None:
        LOGGER.debug("Initialising dimmer channel instance")
        self._dimmer_address = address
        self._channel = channel
        self._id = "edinpluscustomuuid-"+str(self._dimmer_address)+"-"+str(self._channel)
        self.name = name
        self.hub = npu
        self._callbacks = set()
        self._is_on = None
        self._connected = True #Hacked together
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

    # @property
    # def hostname(self):
    #     return self._hostname

    @property
    def is_on(self):
        return self._is_on

    @property
    def brightness(self):
        return self._brightness

    async def set_brightness(self, intensity: int):
        #await async_send_to_npu(self.hub._endpoint,f"$ChanFade,{self._dimmer_address},12,{self._channel},{str(intensity)},0;")
        chan_to_scn_id = f"{str(self._dimmer_address).zfill(3)}-{str(self._channel).zfill(3)}"
        if self.hub._use_chan_to_scn_proxy and chan_to_scn_id in self.hub.chan_to_scn_proxy:
            await tcp_send_message(self.hub.writer,f"$SCNRECALLX,{self.hub.chan_to_scn_proxy[chan_to_scn_id]},{str(intensity)},0;")
            LOGGER.debug(f"TCP tx: $SCNRECALLX,{self.hub.chan_to_scn_proxy[chan_to_scn_id]},{str(intensity)},0;")
        else:
            await tcp_send_message(self.hub.writer,f"$ChanFade,{self._dimmer_address},{self._devcode},{self._channel},{str(intensity)},0;")
            LOGGER.debug(f"TCP tx: $ChanFade,{self._dimmer_address},{self._devcode},{self._channel},{str(intensity)},0;")
        self._brightness = intensity

    async def turn_on(self):
        #await async_send_to_npu(self.hub._endpoint,f"$ChanFade,{self._dimmer_address},12,{self._channel},255,0;")
        chan_to_scn_id = f"{str(self._dimmer_address).zfill(3)}-{str(self._channel).zfill(3)}"
        if self.hub._use_chan_to_scn_proxy and chan_to_scn_id in self.hub.chan_to_scn_proxy:
            await tcp_send_message(self.hub.writer,f"$SCNRECALLX,{self.hub.chan_to_scn_proxy[chan_to_scn_id]},255,0;")
            LOGGER.debug(f"TCP tx: $SCNRECALLX,{self.hub.chan_to_scn_proxy[chan_to_scn_id]},255,0;")
        else:
            await tcp_send_message(self.hub.writer,f"$ChanFade,{self._dimmer_address},{self._devcode},{self._channel},255,0;")
            LOGGER.debug(f"TCP tx: $ChanFade,{self._dimmer_address},{self._devcode},{self._channel},255,0;")
        self._is_on = True

    async def turn_off(self):
        #await async_send_to_npu(self.hub._endpoint,f"$ChanFade,{self._dimmer_address},12,{self._channel},0,0;")
        chan_to_scn_id = f"{str(self._dimmer_address).zfill(3)}-{str(self._channel).zfill(3)}"
        LOGGER.debug(f"chan_to_scn_id: {chan_to_scn_id}")
        LOGGER.debug(f"chan_to_scn_proxy: {self.hub.chan_to_scn_proxy[chan_to_scn_id]}")
        if self.hub._use_chan_to_scn_proxy and chan_to_scn_id in self.hub.chan_to_scn_proxy:
            await tcp_send_message(self.hub.writer,f"$SCNRECALLX,{self.hub.chan_to_scn_proxy[chan_to_scn_id]},0,0;")
            LOGGER.debug(f"TCP tx: $SCNRECALLX,{self.hub.chan_to_scn_proxy[chan_to_scn_id]},0,0;")
        else:
            await tcp_send_message(self.hub.writer,f"$ChanFade,{self._dimmer_address},{self._devcode},{self._channel},0,0;")
            LOGGER.debug(f"TCP tx: $ChanFade,{self._dimmer_address},{self._devcode},{self._channel},0,0;")
        self._is_on = False

    async def tcp_force_state_inform(self):
        LOGGER.debug(f"?CHAN,{self._dimmer_address},{self._devcode},{self._channel};")
        await tcp_send_message(self.hub.writer,f"?CHAN,{self._dimmer_address},{self._devcode},{self._channel};")
    
    async def get_brightness(self):
        LOGGER.warning("Polling using HTTP endpoint")
        output = await async_send_to_npu(self.hub._endpoint,f"?CHAN,{self._dimmer_address},{self._devcode},{self._channel};")
        # Relevant response is in third line starting CHANLEVEL
        # Will be in second line if attempting to call a non existent channel
        brightness = output[2].split(',')[4]
        return brightness

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Light changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)
