import asyncio
import requests
import logging

from homeassistant.core import HomeAssistant

import aiohttp

LOGGER = logging.getLogger(__name__)

# Define consts

DEVCODE_TO_PRODCODE = {
    1: "EVO-LCD-55",
    2: "EVO-SGP-xx",
    4: "EVO-RP-03-02",
    8: "EVS-xxx",
    9: "EVO-INT_CI_xx",
    12: "DIN-02-08",
    14: "DIN-03-04",
    15: "DIN-INT-00-08",
    16: "DIN-RP-05-04",
    17: "DIN-UBC-01-05",
    18: "DIN-DBM-00-08",
    24: "ECO_MULTISENSOR",
    144: "DIN-RP-05-04",
    145: "DIN-UBC-01-05",
}
DEVCODE_TO_PRODNAME = {
    1: "LCD Wall Plate",
    2: "2, 5 and 10 button Wall Plates, Coolbrium & Icon plates",
    4: "Evo 2-channel Relay Module",
    8: "All Evo Slave Packs",
    9: "Evo 4 & 8 channel Contact Input modules",
    12: "eDIN 2A 8 channel dimmer module",
    14: "eDIN 3A 4 channel dimmer module",
    15: "eDIN 8 channel IO module",
    16: "eDIN 5A 4 channel relay module",
    17: "eDIN Universal Ballast Control module",
    18: "eDIN 8 channel Configurable Output module",
    24: "eDIN Mk 1 Multisensor",
    144: "eDIN 5A 4 channel mains sync relay module",
    145: "eDIN Universal Ballast Control 2 module",
}

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
    
    async def discover(self):
        self.lights = await self.async_edinplus_discover_channels()


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
            channel_entity['model'] = DEVCODE_TO_PRODNAME[int(channel.split(',')[2])]
            #print(channel_entity)
            dimmer_channel_instances.append(edinplus_dimmer_channel_instance(channel_entity['address'],channel_entity['channel'],channel_entity['name'],channel_entity['area'],channel_entity['model'],self))

        inputs_csv = [idx for idx in NPU_data if idx.startswith("INPSTATE")]
        for input in inputs_csv:
            # Parsing expected format of Channel,Address,DevCode,ChanNum,AreaNum,ChanName
            input_entity = {}
            input_entity['address'] = int(input.split(',')[1])
            input_entity['channel'] = int(input.split(',')[3])
            input_entity['name'] = input.split(',')[5]
            input_entity['area'] = areas[int(input.split(',')[4])]
            input_entity['model'] = DEVCODE_TO_PRODNAME[int(input.split(',')[2])]
            LOGGER.debug(f"Have found input entity {input_entity['name']} in room {input_entity['area']} but support for inputs has not been added yet.")
            # INPUT ENTITIES CURRENTLY DISABLED
            #print(input_entity)
            #dimmer_channel_instances.append(edinplus_dimmer_channel_instance(channel_entity['address'],channel_entity['channel'],channel_entity['name'],channel_entity['area'],channel_entity['model'],self))

        return dimmer_channel_instances

class edinplus_dimmer_channel_instance:
    def __init__(self, address:int, channel: int, name: str, area: str, model: str, npu: edinplus_NPU_instance) -> None:
        LOGGER.debug("Test message")
        self._dimmer_address = address
        self._channel = channel
        self._id = "edinpluscustomuuid-"+str(self._dimmer_address)+"-"+str(self._channel)
        self.name = name
        self.hub = npu
        self._is_on = None
        self._connected = True #Hacked together
        self._brightness = None
        self.model = model
        self.area = area

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
        await async_send_to_npu(self.hub._endpoint,f"$ChanFade,{self._dimmer_address},12,{self._channel},{str(intensity)},0;")
        self._brightness = intensity

    async def turn_on(self):
        await async_send_to_npu(self.hub._endpoint,f"$ChanFade,{self._dimmer_address},12,{self._channel},255,0;")
        self._is_on = True

    async def turn_off(self):
        await async_send_to_npu(self.hub._endpoint,f"$ChanFade,{self._dimmer_address},12,{self._channel},0,0;")
        self._is_on = False
    
    async def get_brightness(self):
        output = await async_send_to_npu(self.hub._endpoint,f"?CHAN,{self._dimmer_address},12,{self._channel};")
        # Relevant response is in third line starting CHANLEVEL
        # Will be in second line if attempting to call a non existent channel
        brightness = output[2].split(',')[4]
        return brightness

