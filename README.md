# eDIN+ Component (Platform) for Home Assistant

Tested on HA 2022.12.6 and eDIN+ firmware SW00120.2.4.1.44


The state of this component is: Local Push

This component currently communicates with the NPU over a combination of HTTP and TCP using port 26 (not currently configurable)

Inputs currently trigger "edinplus_events" that can be used for automation

## Installation

### Disclaimer

> :warning: This component is still in the alpha stage of development. It is highly likely that you will need to completely remove and reinstall this component in order to upgrade to the latest version, losing any entities defined in automations.

### Via HACS (preferred)

This component can be easily installed via the Home Assistant Community Store (HACS).

If you have not done so already, [follow the instructions to install HACS](https://hacs.xyz/docs/setup/download/) on your HomeAssistant instance.

Following that, [add this repository to the list of custom repositories in HACS](https://github.com/masaccio/ha-kingspan-watchman-sensit), using the following url:

`https://github.com/sftgunner/edinplus-integration`

Then follow the steps in "Configuration" below.

### Manual: adding the eDIN+ Component to Home Assistant
The **edinplus.py** files need to be placed in the installation directory of Home Assistant.
```
<config_dir>/custom_components/edinplus/__init__.py
<config_dir>/custom_components/edinplus/config_flow.py
<config_dir>/custom_components/edinplus/const.py
<config_dir>/custom_components/edinplus/edinplus.py
<config_dir>/custom_components/edinplus/light.py
<config_dir>/custom_components/edinplus/manifest.json
<config_dir>/custom_components/edinplus/strings.json
<config_dir>/custom_components/edinplus/translations/en.json
``` 

Then follow the steps in "Configuration" below.

### Configuration

To setup the eDIN+ component, first ensure HomeAssistant has been rebooted. 

Then add the integration through the integrations page [https://{ip}:8123/config/integrations](https://my.home-assistant.io/redirect/config_flow_start/?domain=edinplus) as you normally would, or click the button below to add it automatically.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=edinplus)

Currently it will prompt for data input without any explanation text - this is the hostname or IP address of the eDIN+ NPU (network processing unit). 

Please ensure it is in the format: "192.168.1.100" (excluding quotes).

## Features

- Autodiscover of all channels configured in NPU
- Dimmer channels from eDIN 2A 8 channel dimmer module (DIN-02-08) are imported as 8 individual lights, with full dimmable control.
- Inputs from either wall plates (EVO-SGP-xx) or contact input modules (EVO-INT_CI_xx) are exposed to HomeAssistant as an `edinplus_event` event. See [the technical information section below](#technical_information) for information on the payload contents. In future, these will be assigned as device triggers for the relevant input channel "device", exposed in HomeAssistant.
- If you have scenes in your NPU that contain a single channel, turning this light on and off will actually control the scene, rather than the output channel directly. This ensures better interoperability between the native eDIN+ system and HomeAssistant.

## eDIN+
More information about the eDIN+ system can be found on Mode Lighting's website: http://www.modelighting.com/products/edin-plus/

## Issues

If you find any bugs, please feel free to submit an issue, pull request or just fork this repo and improve it yourself!

If opening an issue, please could you also include any detail from the HomeAssistant logs (if there are any!): just search for "edinplus" on this page: https://{ip}:8123/config/logs and any error messages should appear (click on them for more detail).

## Technical information

If you're interested in how this integration works, and/or want to help out and improve it, please see the information below for more info!

The integration uses HTTP requests as part of the discovery process, and then communicates with the NPU via a raw TCP/IP stream on port 26.

### API communication

The vast majority of API communication is done via the TCP/IP stream.

HomeAssistant will open a stream on component initialisation using `asyncio`, and then stores the `reader` and `writer` for the connection in the NPU class. These can be called to read and write from the API respectively.

On initialisation, the component will call `$EVENTS,1;` to ensure that the connection is registered for recieving notification of all events happening on the NPU for parsing.

The component will look out for the `!GATRDY;` response on initialisation, but will only put a warning message in the logs if it doesn't see it. In future, there will be better error handling for scenarios like this!

Every half an hour, the component will send the `$OK;` command to keep the connection by alive, queued using the `async_track_time_interval` command. By default, the NPU will close any TCP connection that is inactive for more than an hour.

The method of reading from the TCP stream in "realtime" is somewhat of a hack, but so far has proved robust. The `async_track_time_interval` command is again used to queue a "read from tcp stream" command every 0.01 seconds. This uses the `reader` object stored in the NPU class to see if there are any new bytes sent on the stream. This process will continue to read until an EOF is reached, at which point it will return the contents for the rest of the code to handle. This means it will take 0.05 seconds to read 5 commands that are sent on the TCP stream. To maintain code efficiency, while reading from the stream, a `readlock` flag in the NPU class properties will be set to true. When this is true, the "read from tcp stream" that is queued for that particular 0.01 second will immediately exit. If someone has  a better solution for this, I'd be very appreciative!

### Channel naming

>:warning: Channel naming convention is likely to change

Output channels are named as "{area} {channel name}" (e.g. "Living Room downlighters"), and will automatically be assigned to a HomeAssistant area with the same name as the eDIN+ room.

Input channels are named as "Light switch ({channel name})", and will automatically be assigned to a HomeAssistant area with the same name as the eDIN+ room.

### Discovery

Discovery is completed by calling the `/info?what=names` endpoint on the NPU via HTTP. This returns a full list of all devices, areas and scenes on the NPU in CSV format.

At present, only lines starting `CHAN` and `INPSTATE` are read as ouput channels and input channels respectively. It is a known issue that `INPSTATE` doesn't read each channel from wall plates.

One-to-one channel-to-scene mapping is done by requesting all scenes via `?SCNNAMES;` and then `?SCNCHANNAMES,{scene};`. If a scene controls only a single channel, then instead of using `$ChanFade,...` to control the channel output, `$SCNRECALLX,...` is used instead.

### edinplus_event information

`edinplus_event` events contain the following information:

- address: Device address [int]
- device: Device full name [str]
- channel: Channel on device that has been triggered [int]
- newstate: The new state (e.g. 1 for "Press-on") [int]
- newstate_desc: The english version of the new state (e.g "Press-on") [str]
- description: A generic description of the event type [str]
- raw: The raw API call recieved to trigger the event [str]

A full list of the different button states can be found in `const.py` under `NEWSTATE_TO_BUTTONEVENT`.