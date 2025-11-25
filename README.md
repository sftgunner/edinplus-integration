# eDIN+ Component (Platform) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)

Tested on HA 2022.12.6 - 2025.11.0 and eDIN+ firmware SW00120.2.4.1.44 - SW00120.2.4.2.37. 

Please note eDIN+ firmware SW00120.2.3.x.x is **NOT** currently supported, as it doesn't support device discovery. 

You can find your NPU firmware version in "Settings & Upgrades" -> "Upgrade & Backups" -> "Firmware Maintenance". If you are running an older firmware please contact Mode Technical support (see [#11](https://github.com/sftgunner/edinplus-integration/issues/11)).

The state of this component is Local Push

This component communicates with the NPU over a combination of HTTP and TCP using port 26

Inputs (keypads, IO modules etc) generate device triggers that can be used in HA automations automation

## Installation via HACS

> :warning: _This component is still in development. It is possible that you will need to completely remove and reinstall this component in order to upgrade to the latest version, losing any entities defined in automations._

This component can be easily installed via the Home Assistant Community Store (HACS).

If you have not done so already, [follow the instructions to install HACS](https://hacs.xyz/docs/setup/download/) on your HomeAssistant instance.

Following that, install the eDIN+ integration using the button below:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sftgunner&repository=edinplus-integration&category=integration)

Then follow the steps in ["Configuration"](#configuration) below.

This method allows for installing updates through HACS.

### Configuration

To set up the eDIN+ component, first ensure HomeAssistant has been rebooted after completing the HACS installation process above.

Then add the integration through the integrations page [https://{ip}:8123/config/integrations](https://my.home-assistant.io/redirect/config_flow_start/?domain=edinplus) as you normally would, or click the button below to add it automatically.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=edinplus)

#### Configuration options

| Option | Description | Default | 
| --- | --- | --- |
|Hostname | IP address (or hostname) of the eDIN+ NPU | |
|TCP Port | Gateway control port (as found on NPU in Settings -> Network services -> Enable gateway control -> Use port) | 26 |
|Use channel-to-scene proxy| Whether to try and link channels to scenes to inherit fade | enabled|
|Automatically suggest and create areas | The integration will try and assign Mode devices to areas with the same name as in eDIN+, and will create them in HA if they don't already exist | enabled|
|Keep-alive interval | How often HA will check that the NPU is still online | 10 |
|Keep-alive timeout | How long HA will wait for a reply from the NPU when checking it's still online | 2 |
|System info interval | How often HA will check that no devices have been added/removed from the NPU that it needs to rediscover | 300 |
|Intial reconnect delay| If a connection is lost, how long will HA wait (minimum) between reconnection attempts | 60† |
|Max reconnect delay| If a connection is lost, how long will HA wait (maximum) between reconnection attempts | 180† |

† These settings will depend on whether the NPU has TCP keepalive enabled or disabled. The integration will be able to recover from outages faster with it enabled, but it is classed by Mode Lighting as an "advanced feature". 

**If you enable TCP keepalive and leave the Idle time at the default 120s, you can leave the reconnect settings at default** 

Please adjust as needed:
- Disabled (default from mode):
  - Initial delay: 900s
  - Max delay: 3600s
- Enabled:
  - Initial delay: ```(Idle time + 60s) / 3``` (180s / 3 = 60s by default)
  - Max delay: ```Idle time + 60s``` (120s + 60s = 180s by default)

#### Post-configuration

HomeAssistant will then automatically discover all devices connected to the NPU, and will automatically suggest Home Assistant areas for each device based on their "room" in the eDIN+ configuration. Please note that lighting devices (dimmer channels) may not immediately appear after install/configuration.

## Features

- Auto-discovery of all compatible channels configured in NPU
- Dimmer channels from eDIN 2A 8 channel dimmer module (DIN-02-08) are imported as 8 individual lights, with full dimmable control.
- Output channels from Input-Output Module (DIN-INT-00-08-PLUS) are imported as individual light entities, with dimmable control.
- Any normal switched channels (i.e. non-dimmable channels) from any module will be imported as dimmable light entities. This is due to the design of the eDIN+ API - the NPU will handle dimming logic, and will NOT let any dimming commands be sent by HomeAssistant to a channel labelled as normal switched in the eDIN+ interface.
- Inputs from either wall plates (EVO-SGP-xx), I/O modules (DIN-INT-00-08-PLUS) or contact input modules (EVO-INT_CI_xx) are exposed to HomeAssistant as device triggers, which can be used in automations.
- Relay contact channels from Relay Module (DIN-MSR-05-04-PLUS) are imported as individual switch entities. The state of these relays can be controlled from this switch entity, or can be temporarily toggled for 1s (pulse) using a "Pulse toggle" button entity in HomeAssistant.
- Supports multiple NPUs connected to a single HomeAssistant instance (and equally up to 3 HomeAssistant instances are able to access the same NPU).
- If you have scenes in your NPU that contain a single lighting output channel, turning this light on and off will actually control the scene, rather than the output channel directly. These scenes are termed "Proxy Scenes" within this integration; this ensures better interoperability between the native eDIN+ system and HomeAssistant.

## Compatible modules/controls
| Device name                      | Model No.            | Supported?            |
|----------------------------------|----------------------|-----------------------|
| Network Processor Module         | DIN-NPU-00-01-PLUS   | :white_check_mark:    |
| Power Supply Module              | DIN-PSU-24V-PLUS     | :white_check_mark:    |
| 8 Channel Dimmer Module          | DIN-02-08-PLUS       | :white_check_mark:    |
| 4 Channel Dimmer Module - TE     | DIN-02-04-TE-PLUS    | :warning:[^1]         |
| 4 Channel Dimmer Module          | DIN-03-04-PLUS       | :warning:[^1]         |
| DALI Broadcast Module            | DIN-DBM-32-08-PLUS   | :x:                   |
| 4 Channel Relay Contact Module   | DIN-MSR-05-04-PLUS   | :white_check_mark:    |
| Input-Output Module              | DIN-INT-00-08-PLUS   | :warning:[^2]         |
| Universal Ballast Control Module | DIN-UBC-01-05-PLUS   | :x:         |
| 4 Port M-BUS Splitter Module     | DIN-MBUS-SPL-04-PLUS | :warning:[^3]         |
| Mode Sensor                      | DIN-MSENS-RM-T       | :x:                   |
| Touch Screen 7" Tablet           | DIN-TS-07            | :x:                   |
| Oslo Rotary controls             | DIN-RD-00-xx         | :x:                   |
| EVO LCD Wall plate               | EVO-LCD-xx           | :white_check_mark:[^4]|
| Wall Plates (2, 5 and 10 button) | EVO-SGP-xx           | :white_check_mark:[^5]|
| Contact Input Module             | EVO-INT-CI-xx        | :white_check_mark:    |

[^1]: These aren't officially supported yet as I don't have the hardware to validate with, but functionality should be pretty close to the DIN-02-08-PLUS. If you use this device, it will flag up as a warning in the logs - please open an issue to confirm either that it functions as intended or to report any bugs, and I'll update this page accordingly.
[^2]: 0-10V output and contact inputs are supported. Output channels will report their state as being "On" or "Off" (i.e. open or closed) using a sensor. DMX outputs are not supported.
[^3]: These modules should not require any extra code to work, but haven't been verified to ensure that they don't cause issues.
[^4]: Input signals (device triggers) from this device are supported, but there is not currently any support for changing the text or button colour.
[^5]: Due to limitations of the NPU, all wall plates are assumed to be 10 button. These wall plates include Coolbrium, iCON, Geneva and EVO-Ellipse styles. There is not currently any support for changing the button colour


## eDIN+
More information about the eDIN+ system can be found on Mode Lighting's website: http://www.modelighting.com/products/edin-plus/.

## Using inputs (wall plates/contact modules) in automations

> :warning: _These instructions are up to date as of 2023.8. If using a newer version of HomeAssistant, you may experience some inconsistencies in your interface._

Input channels are imported as devices into HomeAssistant, but most don't have any entities assigned to them. The most reliable way to use them as triggers for automation, is to use the built-in device triggers. It is worth noting that I/O module input channels also have a Sensor assigned to them, to designate whether they are on or off. While this sensor can be used for automation, it is slower and offers fewer options than using the device triggers.

### Method 1 - via the devices page

1. Navigate to the [devices page](https://my.home-assistant.io/redirect/devices/) in your HomeAssistant instance, and select the input channel/switch you wish to use for your automation. 
1. In the Automations panel, click or tap on the blue plus icon, and click on "Show N more..."
1. Select one of "Release-off", "Press-on", "Hold-on", "Short-press", "Hold-off" as the trigger for your automation. For wall plates, there will be 50 different options, with each of the aforementioned options preceded by "Button {1-10}", e.g. "Button 4 Press-on".
1. Continue to create your automation accordingly

### Method 2 - via the automations page

1. Navigate to the [automations page](https://my.home-assistant.io/redirect/automations/) in your HomeAssistant instance, and select the "Create Automation" button. 
1. Select "Create new automation"
1. Select "Add trigger", and then click or tap on "Device"
1. Select the switch/input device you wish to use as the trigger
1. Select the trigger type (i.e. one of "Release-off", "Press-on", "Hold-on", "Short-press", "Hold-off"). For wall plates, there will be 50 different options, with each of the aforementioned options preceded by "Button {1-10}", e.g. "Button 4 Press-on".
1. Continue to create your automation accordingly

## Adding curtains/blinds as HomeAssistant cover entities

> :warning: _These instructions are up to date as of 2023.8. If using a newer version of HomeAssistant, you may experience some inconsistencies in your interface._

HomeAssistant uses [cover entities](https://www.home-assistant.io/integrations/cover/) to represent curtains, blinds, garage doors etc. If you have integrated your curtains and/or blinds into eDIN+ using the 4 x 5A Relay Unit, it is possible to add your curtains into HomeAssistant as fully fledged cover entities. 

Unfortunately, as there are so many different types of electronic blinds and curtains, it is impossible to create an exhaustive guide on how to configure them in eDIN+ and HomeAssistant. The information below serves as a guide for a basic curtain setup, and can be adapted to suit the needs of individual configurations as required by the end user.

To do this, a template entity is used. Simply navigate to your configuration.yaml file ([instructions on how to edit can be found at this link](https://www.home-assistant.io/docs/configuration/#:~:text=Editing%20configuration.yaml,File%20Editor%20add%2Don%20instead.)), and then add the following snippet of code at the bottom of your file.

Curtain and blind motors each work differently - the example below is for a BCM700D curtain motor, which needs just a short pulse to trigger opening and closing functionality. Blinds that need the relay to be closed for a longer period of time might be able to achieve this by using [scripts](https://www.home-assistant.io/integrations/script/) instead of the `button.press` service.

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

:warning: Please note, the state of this entity can only be set by HomeAssistant. If you control your curtains/blinds using eDIN+ directly, the state of the cover entity in HomeAssistant will NOT be updated - this is a limitation of the template entity. If your curtains/blinds have some sort of feedback mechanism for reporting open/close state, you may be able to adapt the template using a sensor input from an I/O interface, but this is a suggestion only, and has NOT been tested by the developer of this integration.

## Issues

If you find any bugs, please feel free to submit an issue, pull request or just fork this repo and improve it yourself!

If opening an issue, please could you also include any detail from the HomeAssistant logs (if there are any!): just search for "edinplus" on this page: [http://{ip}:8123/config/logs](https://my.home-assistant.io/redirect/logs/) and any error messages should appear (click on them for more detail).

If a module doesn't work as expected, please check it appears in the list of [compatible modules/controls](https://github.com/sftgunner/edinplus-integration/blob/main/README.md#compatible-modulescontrols) before submitting an issue. If your module does not appear in this list, it is not expected that it will work with this integration. As I am only able to develop for the hardware I have, it is unlikely that I'll be able to add support for any modules not listed above. Having said that, please feel free to implement it yourself and then submit a pull request!

## Technical information

If you're interested in how this integration works, and/or want to help out and improve it, please see the information below for more info!

The integration uses HTTP requests as part of the discovery process, and then communicates with the NPU via a raw TCP/IP stream on port 26.

### API communication

The vast majority of API communication is done via the TCP/IP stream.

HomeAssistant will open a stream on component initialisation using `asyncio`, and then stores the `reader` and `writer` for the connection in the NPU class. These can be called to read and write from the API respectively.

On initialisation, the component will call `$EVENTS,1;` to ensure that the connection is registered for receiving notification of all events happening on the NPU for parsing.

The component will look out for the `!GATRDY;` response on initialisation, but will only put a warning message in the logs if it doesn't see it. In future, there will be better error handling for scenarios like this!

Every half an hour, the component will send the `$OK;` command to keep the connection alive, queued using the `async_track_time_interval` command. By default, the NPU will close any TCP connection that is inactive for more than an hour.

The method of reading from the TCP stream in "realtime" is somewhat of a hack, but so far has proved robust. The `async_track_time_interval` command is again used to queue a "read from tcp stream" command every 0.01 seconds. This uses the `reader` object stored in the NPU class to see if there are any new bytes sent on the stream. This process will continue to read until an EOF is reached, at which point it will return the contents for the rest of the code to handle. This means it will take 0.05 seconds to read 5 commands that are sent on the TCP stream. To maintain code efficiency, while reading from the stream, a `readlock` flag in the NPU class properties will be set to true. When this is true, the "read from tcp stream" that is queued for that particular 0.01 second will immediately exit. If someone has a better solution for this, I'd be very appreciative!

### Channel naming

>:warning: _Channel naming convention may change in the future_

Lighting and relay channels are assigned to their own device in HomeAssistant so that they can each be assigned to their own room. By contrast, keypads are kept as one HomeAssistant device for all 10 buttons, as these will always be in the same room.

Output channels are named as "{area} {channel name}" (e.g. "Living Room downlighters"), and will automatically be assigned to a HomeAssistant area with the same name as the eDIN+ room.

Input channels are named as "{area} {channel name} switch" (e.g. "Living Room downlighters switch") for contact modules or I/O modules, or "{area} {plate name}" (e.g. Bedroom Keypad) for wall plates. Input channels will automatically be assigned to a HomeAssistant area with the same name as the eDIN+ room.

### Discovery

Discovery is completed by calling the `/info?what=names` endpoint on the NPU via HTTP. This returns a full list of all devices, areas and scenes on the NPU in CSV format. Unfortunately this info endpoint doesn't exist in SW00.120.2.3.x.x, meaning any systems on this firmware aren't able to complete discovery correctly. 

At present, only lines starting `CHAN` and `INPSTATE` are read as output channels and input channels respectively.

One-to-one channel-to-scene mapping for proxy scenes are done using regex on the `/info?what=levels` endpoint on the NPU via HTTP. If a scene controls only a single channel, then instead of using `$ChanFade,...` to control the channel output, `$SCNRECALLX,...` is used instead.
