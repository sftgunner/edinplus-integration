import asyncio
import requests
import logging

LOGGER = logging.getLogger(__name__)

def sendToEdin(endpoint,data):
    response = requests.post(endpoint, data = data)
    return response.content.decode("utf-8").splitlines()

class EdinPlusLightChannelInstance:
    def __init__(self, hostname:str, address:int, channel: int) -> None:
        LOGGER.debug("Test message")
        self._dimmer_address = address
        self._channel = channel
        self._hostname = hostname
        #NB although the 1 doesn't exist in the Edin+ API spec for endpoint, it's the only way to stop requests from stripping it completely (which results in /gateway, a 404)
        self._endpoint = f"http://{hostname}/gateway?1" 
        self._is_on = None
        self._connected = True #Hacked together
        self._brightness = None

    @property
    def channel(self):
        return self._channel

    @property
    def hostname(self):
        return self._hostname

    @property
    def is_on(self):
        return self._is_on

    @property
    def brightness(self):
        return self._brightness

    def set_brightness(self, intensity: int):
        sendToEdin(self._endpoint,f"$ChanFade,1,12,{self._channel},{str(intensity)},0;")
        self._brightness = intensity

    def turn_on(self):
        sendToEdin(self._endpoint,f"$ChanFade,1,12,{self._channel},255,0;")
        self._is_on = True

    def turn_off(self):
        sendToEdin(self._endpoint,f"$ChanFade,1,12,{self._channel},0,0;")
        self._is_on = False
    
    #def get_brightness(self):
        

def EdinPlusDiscoverChannels(hostname):
    
    edinEndpoint = f"http://{hostname}/gateway?1" #NB although the 1 doesn't exist in the Edin+ API spec, it's the only way to stop requests from stripping it completely (which results in /gateway, a 404)

    areaList = sendToEdin(edinEndpoint,"?AREANAMES;")

    print(areaList)

    areaIDs = []
    areaNames = []
    foundChannelIdxs = []
    channels = []

    for idx in range(1,len(areaList)): #Skip the first as this is just an OK command
        currentArea = str(areaList[idx]).split(",")
        # Check that the area actually has scenes and channels (channels = is odd, has scenes is 3 or 7)
        if (int(currentArea[3]) == 3) or (int(currentArea[3]) == 7):
            currentAreaID = currentArea[1]
            currentAreaName = currentArea[4][:-1] #Last character will be ;, so we strip it
            areaIDs.append(currentAreaID)
            areaNames.append(currentAreaName)
        else:
            print(f"Area {currentArea[4]} doesn't have any channels ({currentArea[3]}), or it doesn't have scenes so we can't interogate it")

    print(areaNames)
    print(len(areaIDs))
    for areaIdx in range(0,len(areaIDs)):
        print(f"AREA ID {areaIDs[areaIdx]} - {areaNames[areaIdx]}")
        # Get a list of all scene names that apply to this area
        sceneList = sendToEdin(edinEndpoint,f"?SCNNAMES,{areaIDs[areaIdx]};")
        sceneIDs = []
        for sceneIdx in range(1,len(sceneList)):
            currentScene = str(sceneList[sceneIdx]).split(",")
            sceneIDs.append(currentScene[1]);
        print(sceneIDs)
        for sceneID in sceneIDs:
            channelList = sendToEdin(edinEndpoint,f"?SCNCHANNAMES,{sceneID};")
            print(channelList)
            for channelIdx in range(1,len(channelList)):
                currentChannel = str(channelList[channelIdx]).split(",")
                if currentChannel[3] in foundChannelIdxs:
                    print(f"Already found channel {currentChannel[3]}. Not reassigning room")
                else:
                    channels.append({"name":f"{areaNames[areaIdx]} {currentChannel[6][:-1]}","address":currentChannel[1],"channel":currentChannel[3],"hostname":hostname})
                    foundChannelIdxs.append(currentChannel[3])

    return channels