# eDIN+ Component (Platform) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)

Tested on HA 2022.12.6 - 2023.8 and eDIN+ firmware SW00120.2.4.1.44. 

Please note eDIN+ firmware SW00.120.2.3.x.x is **NOT** currently supported.

The state of this component is: Local Push

This component communicates with the NPU over a combination of HTTP and TCP using port 26

Inputs trigger device triggers that can be used for automation

## Installation via HACS

### Disclaimer

> :warning: This component is still in development. It is highly likely that you will need to completely remove and reinstall this component in order to upgrade to the latest version, losing any entities defined in automations.

This component can be easily installed via the Home Assistant Community Store (HACS).

If you have not done so already, [follow the instructions to install HACS](https://hacs.xyz/docs/setup/download/) on your HomeAssistant instance.

Following that, install the eDIN+ integration using the button below:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sftgunner&repository=edinplus-integration&category=integration)

Then follow the steps in ["Configuration"](#configuration) below.

This method allows for installing updates through HACS.

### Configuration

To setup the eDIN+ component, first ensure HomeAssistant has been rebooted. 

Then add the integration through the integrations page [https://{ip}:8123/config/integrations](https://my.home-assistant.io/redirect/config_flow_start/?domain=edinplus) as you normally would, or click the button below to add it automatically.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=edinplus)

When prompted, please enter the hostname or IP address of the eDIN+ NPU (network processing unit). Please ensure it is in the format: "192.168.1.100" (excluding quotes).

HomeAssistant will then automatically discover all devices connected to the NPU, and will automatically suggest Home Assistant areas for each device based on their "room" in the eDIN+ configuration. Please note that lighting devices (dimmer channels) may not immediately appear after install/configuration.

## Features

- Autodiscover of all channels configured in NPU
- Dimmer channels from eDIN 2A 8 channel dimmer module (DIN-02-08) are imported as 8 individual lights, with full dimmable control.
- Inputs from either wall plates (EVO-SGP-xx), I/O modules (DIN-INT-00-08-PLUS) or contact input modules (EVO-INT_CI_xx) are exposed to HomeAssistant as device triggers.
- If you have scenes in your NPU that contain a single channel, turning this light on and off will actually control the scene, rather than the output channel directly. These scenes are termed "Proxy Scenes" within this integration; this ensures better interoperability between the native eDIN+ system and HomeAssistant.
- Supports multiple NPUs connected to a single HomeAssistant instance (and equally up to 3 HomeAssistant instances are able to access the same NPU)

## Compatible modules/controls
| Device name                      | Model No.            | Supported?            |
|----------------------------------|----------------------|-----------------------|
| Network Processor Module         | DIN-NPU-00-01-PLUS   | :white_check_mark:    |
| Power Supply Module              | DIN-PSU-24V-PLUS     | :white_check_mark:    |
| 8 Channel Dimmer Module          | DIN-02-08-PLUS       | :white_check_mark:    |
| 4 Channel Dimmer Module - TE     | DIN-02-04-TE-PLUS    | :x:[^1]               |
| 4 Channel Dimmer Module          | DIN-03-04-PLUS       | :x:[^1]               |
| DALI Broadcast Module            | DIN-DBM-32-08-PLUS   | :x:                   |
| 4 Channel Relay Contact Module   | DIN-MSR-05-04-PLUS   | :white_check_mark:    |
| Input-Output Module              | DIN-INT-00-08-PLUS   | :warning:[^2]         |
| Universal Ballast Control Module | DIN-UBC-01-05-PLUS   | :warning:[^3]         |
| 4 Port M-BUS Splitter Module     | DIN-MBUS-SPL-04-PLUS | :warning:[^3]         |
| Mode Sensor                      | DIN-MSENS-RM-T       | :x:                   |
| Touch Screen 7" Tablet           | DIN-TS-07            | :x:                   |
| Oslo Rotary controls             | DIN-RD-00-xx         | :x:                   |
| EVO LCD Wall plate               | EVO-LCD-xx           | :x:                   |
| Wall Plates (2, 5 and 10 button) | EVO-SGP-xx           | :white_check_mark:[^4]|
| Contact Input Module             | EVO-INT-CI-xx        | :white_check_mark:    |

[^1]: These aren't supported yet as I don't have the hardware to validate with, but should be simple to add as they're very similar to the DIN-02-08-PLUS. If you have this device and happy to help with a bit of debugging if needed, please open an issue and I'll trial adding these.
[^2]: 0-10V output and contact inputs are supported. DMX outputs are not supported. A sensor reading output states is not yet supported.
[^3]: These modules should not require any extra code to work, but haven't been verified to ensure that they don't cause issues.
[^4]: Due to limitations of the NPU, all wall plates are assumed to be 10 button. These wall plates include Coolbrium, iCON, Geneva and EVO-Ellipse styles.


## eDIN+
More information about the eDIN+ system can be found on Mode Lighting's website: http://www.modelighting.com/products/edin-plus/

## Issues

If you find any bugs, please feel free to submit an issue, pull request or just fork this repo and improve it yourself!

If opening an issue, please could you also include any detail from the HomeAssistant logs (if there are any!): just search for "edinplus" on this page: https://{ip}:8123/config/logs and any error messages should appear (click on them for more detail).

If a module doesn't work as expected, please check it appears in the list of [compatible modules/controls](https://github.com/sftgunner/edinplus-integration/README.md#compatible-modulescontrols) before submitting an issue. If your module does not appear in this list, it is not expected that it will work with this integration. As I am only able to develop for the hardware I have, it is unlikely that I'll be able to add support for any modules not listed above. Having said that, please feel free to implement it yourself and then submit a pull request!

## Adding curtains/blinds as HomeAssistant cover entities

HomeAssistant uses [cover entites](https://www.home-assistant.io/integrations/cover/) to represent curtains, blinds, garage doors etc. If you have integrated your curtains and/or blinds into eDIN+ using the 4 x 5A Relay Unit, it is easy to add your curtains into HomeAssistant as fully fledged cover entities. 

Unfortunately, as there are so many different types of electronic blinds and curtains, it is impossible to create an exhaustive guide on how to configure them in eDIN+ and HomeAssistant. The information below serves as a guide for a basic curtain setup, and can be adapted to suit the needs of individual configurations as required.

To do this, a template entity is used. Simply navigate to your configuration.yaml file ([instructions on how to edit can be found at this link](https://www.home-assistant.io/docs/configuration/#:~:text=Editing%20configuration.yaml,File%20Editor%20add%2Don%20instead.)), and then add the following snippet of code at the bottom of your file.

Curtain and blind motors each work differently - the example below is for a BCM700D curtain motor, which needs just a short pulse to trigger opening and closing functionality. Blinds that need the relay to be closed for a longer period of time might be able to achieve this by using [scripts](https://www.home-assistant.io/integrations/script/) instead of the button.press service.

```yaml
cover:
  - platform: template
    covers:
      test_curtains:
        device_class: curtain
        friendly_name: "Test Curtain entity"
        open_cover:
          service: button.press
          target:
            entity_id: button.relay1
        close_cover:
          service: button.press
          target:
            entity_id: button.relay2
```
In this example, you would switch out ```button.relay1``` and ```button.relay2``` for the relevant pulse toggle buttons. If you were using blinds or a garage door rather than curtains, you can change the ```device class``` accordingly, using any of the classes found [in the HomeAssistant docs](https://www.home-assistant.io/integrations/cover/#device-class).

If you want to add multiple curtains, simply copy and paste from ```test_curtains``` onwards.

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

>:warning: Channel naming convention may change in the future

Lighting and relay channels are assigned to their own device in HomeAssistant so that they can each be assigned to their own room. By contrast, keypads are kept as one HomeAssistant device for all 10 buttons, as these will always be in the same room.

Output channels are named as "{area} {channel name}" (e.g. "Living Room downlighters"), and will automatically be assigned to a HomeAssistant area with the same name as the eDIN+ room.

Input channels are named as "{area} {channel name} switch" (e.g. "Living Room downlighters switch") for contact modules, or "{area} {plate name} button {N}" (e.g. Bedroom Keypad button 2) for wall plates. Input channels will automatically be assigned to a HomeAssistant area with the same name as the eDIN+ room.

### Discovery

Discovery is completed by calling the `/info?what=names` endpoint on the NPU via HTTP. This returns a full list of all devices, areas and scenes on the NPU in CSV format. Unfortunately this info endpoint doesn't exist in SW00.120.2.3.x.x, meaning any systems on this firmware aren't able to complete discovery correctly. 

At present, only lines starting `CHAN` and `INPSTATE` are read as ouput channels and input channels respectively.

One-to-one channel-to-scene mapping for proxy scenes are done using regex on the `/info?what=levels` endpoint on the NPU via HTTP. If a scene controls only a single channel, then instead of using `$ChanFade,...` to control the channel output, `$SCNRECALLX,...` is used instead.
