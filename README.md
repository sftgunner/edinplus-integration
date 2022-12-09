# eDIN+ Component (Platform) for Home Assistant

Tested on HA 2022.11.3 and eDIN+ firmware SW00120.2.4.1.44

Currently there is only support for brightness control using the 8Ch Dimmer.

Lighting channels must be assigned to a scene in order to be discovered.

The state of this component is: Local Polling

## Installation
### Adding the eDIN+ Component to Home Assistant
The **edinplus.py** files need to be placed in the installation directory of Home Assistant. For me this is
```
<config_dir>/custom_components/edinplus/__init__.py
<config_dir>/custom_components/edinplus/conifg_flow.py
<config_dir>/custom_components/edinplus/edinplus.py
<config_dir>/custom_components/edinplus/light.py
<config_dir>/custom_components/edinplus/manifest.json
``` 
There are instructions to follow on the instructions on the home-assistant website. If you need help, let me know.

### Configuring the eDIN+ component

To setup the eDIN+ component, first ensure homeassistant has been rebooted. Then add the integration through the integrations page https://{ip}:8123/config/integrations as you normally would. 

Currently it will prompt for data input without any explanation text - this is the hostname or IP address of the eDIN+ NPU (network processing unit). 

Please ensure it is in the format: "192.168.1.100" (excluding quotes). 

From there, it should autodiscover all channels that are assigned to scenes.

## eDIN+
More information about the eDIN+ system can be found on Mode Lighting's website: http://www.modelighting.com/products/edin-plus/

## Issues

If you find any bugs, please feel free to submit an issue, pull request or just fork this repo and improve it yourself!

If opening an issue, please could you also include any detail from the HomeAssistant logs (if there are any!): just search for "edinplus" on this page: https://{ip}:8123/config/logs and any error messages should appear (click on them for more detail).

## Next priorities

The current priorities are:
 - Change the discovery method to use the /info endpoint
 - Switch from polling using asynchronous HTTP requests to instead listen to the socket stream
 - Add the input modules as entities and add inputs as triggers
 - Add support for passing the scenes in eDIN+ to HomeAssistant so scenes can be used in automations rather than overriding channels
 - Ensure the integration is robust (with proper error handling and aiming to satisfy all integration standards https://developers.home-assistant.io/docs/creating_component_code_review)

