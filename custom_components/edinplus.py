import asyncio
import requests
import logging

from homeassistant.core import HomeAssistant

import aiohttp

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

class edinplus_NPU_instance:
    def __init__(self,hass: HomeAssistant,hostname:str) -> None:
        LOGGER.debug("Initialising NPU")
        self._hostname = hostname
        self._hass = hass
        #NB although the 1 doesn't exist in the Edin+ API spec for endpoint, it's the only way to stop requests from stripping it completely (which results in /gateway, a 404)
        self._endpoint = f"http://{hostname}/gateway?1"
        self.lights = []
    
    async def discover(self):
        self.lights = await self.EdinPlusDiscoverChannels()

    async def EdinPlusDiscoverChannels(self):
    
        areaList = await async_send_to_npu(self._endpoint,"?AREANAMES;")

        LOGGER.debug(areaList)

        areaIDs = []
        areaNames = []
        foundChannelIdxs = []
        dimmer_channel_instances = []

        for idx in range(1,len(areaList)): #Skip the first as this is just an OK command
            currentArea = str(areaList[idx]).split(",")
            # Check that the area actually has scenes and channels (channels = is odd, has scenes is 3 or 7)
            if (int(currentArea[3]) == 3) or (int(currentArea[3]) == 7):
                currentAreaID = currentArea[1]
                currentAreaName = currentArea[4][:-1] #Last character will be ;, so we strip it
                areaIDs.append(currentAreaID)
                areaNames.append(currentAreaName)
            else:
                LOGGER.debug(f"Area {currentArea[4]} doesn't have any channels ({currentArea[3]}), or it doesn't have scenes so we can't interogate it")

        LOGGER.debug(areaNames)
        LOGGER.debug(len(areaIDs))
        for areaIdx in range(0,len(areaIDs)):
            LOGGER.debug(f"AREA ID {areaIDs[areaIdx]} - {areaNames[areaIdx]}")
            # Get a list of all scene names that apply to this area
            sceneList = await async_send_to_npu(self._endpoint,f"?SCNNAMES,{areaIDs[areaIdx]};")
            sceneIDs = []
            for sceneIdx in range(1,len(sceneList)):
                currentScene = str(sceneList[sceneIdx]).split(",")
                sceneIDs.append(currentScene[1]);
            LOGGER.debug(sceneIDs)
            for sceneID in sceneIDs:
                channelList = await async_send_to_npu(self._endpoint,f"?SCNCHANNAMES,{sceneID};")
                LOGGER.debug(channelList)
                for channelIdx in range(1,len(channelList)):
                    currentChannel = str(channelList[channelIdx]).split(",")
                    if currentChannel[3] in foundChannelIdxs:
                        LOGGER.debug(f"Already found channel {currentChannel[3]}. Not reassigning room")
                    else:
                        #channels.append({"name":f"{areaNames[areaIdx]} {currentChannel[6][:-1]}","address":currentChannel[1],"channel":currentChannel[3],"hostname":hostname})
                        dimmer_channel_instances.append(edinplus_dimmer_channel_instance(currentChannel[1],currentChannel[3],f"{areaNames[areaIdx]} {currentChannel[6][:-1]}",self))
                        foundChannelIdxs.append(currentChannel[3])

        return dimmer_channel_instances

class edinplus_dimmer_channel_instance:
    def __init__(self, address:int, channel: int, name: str, npu: edinplus_NPU_instance) -> None:
        LOGGER.debug("Test message")
        self._dimmer_address = address
        self._channel = channel
        self.name = name
        #self._hostname = hostname
        self.hub = npu
        #NB although the 1 doesn't exist in the Edin+ API spec for endpoint, it's the only way to stop requests from stripping it completely (which results in /gateway, a 404)
        #self._endpoint = f"http://{hostname}/gateway?1" 
        self._is_on = None
        self._connected = True #Hacked together
        self._brightness = None

    @property
    def channel(self):
        return self._channel

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
        await async_send_to_npu(self.hub._endpoint,f"$ChanFade,1,12,{self._channel},{str(intensity)},0;")
        self._brightness = intensity

    async def turn_on(self):
        await async_send_to_npu(self.hub._endpoint,f"$ChanFade,1,12,{self._channel},255,0;")
        self._is_on = True

    async def turn_off(self):
        await async_send_to_npu(self.hub._endpoint,f"$ChanFade,1,12,{self._channel},0,0;")
        self._is_on = False
    
    #def get_brightness(self):
        

# async def EdinPlusDiscoverChannels(hostname):
    
#     edinEndpoint = f"http://{hostname}/gateway?1" #NB although the 1 doesn't exist in the Edin+ API spec, it's the only way to stop requests from stripping it completely (which results in /gateway, a 404)

#     areaList = await async_send_to_npu(edinEndpoint,"?AREANAMES;")

#     LOGGER.debug(areaList)

#     areaIDs = []
#     areaNames = []
#     foundChannelIdxs = []
#     channels = []

#     for idx in range(1,len(areaList)): #Skip the first as this is just an OK command
#         currentArea = str(areaList[idx]).split(",")
#         # Check that the area actually has scenes and channels (channels = is odd, has scenes is 3 or 7)
#         if (int(currentArea[3]) == 3) or (int(currentArea[3]) == 7):
#             currentAreaID = currentArea[1]
#             currentAreaName = currentArea[4][:-1] #Last character will be ;, so we strip it
#             areaIDs.append(currentAreaID)
#             areaNames.append(currentAreaName)
#         else:
#             LOGGER.debug(f"Area {currentArea[4]} doesn't have any channels ({currentArea[3]}), or it doesn't have scenes so we can't interogate it")

#     LOGGER.debug(areaNames)
#     LOGGER.debug(len(areaIDs))
#     for areaIdx in range(0,len(areaIDs)):
#         LOGGER.debug(f"AREA ID {areaIDs[areaIdx]} - {areaNames[areaIdx]}")
#         # Get a list of all scene names that apply to this area
#         sceneList = await async_send_to_npu(edinEndpoint,f"?SCNNAMES,{areaIDs[areaIdx]};")
#         sceneIDs = []
#         for sceneIdx in range(1,len(sceneList)):
#             currentScene = str(sceneList[sceneIdx]).split(",")
#             sceneIDs.append(currentScene[1]);
#         LOGGER.debug(sceneIDs)
#         for sceneID in sceneIDs:
#             channelList = await async_send_to_npu(edinEndpoint,f"?SCNCHANNAMES,{sceneID};")
#             LOGGER.debug(channelList)
#             for channelIdx in range(1,len(channelList)):
#                 currentChannel = str(channelList[channelIdx]).split(",")
#                 if currentChannel[3] in foundChannelIdxs:
#                     LOGGER.debug(f"Already found channel {currentChannel[3]}. Not reassigning room")
#                 else:
#                     channels.append({"name":f"{areaNames[areaIdx]} {currentChannel[6][:-1]}","address":currentChannel[1],"channel":currentChannel[3],"hostname":hostname})
#                     foundChannelIdxs.append(currentChannel[3])

#     return channels