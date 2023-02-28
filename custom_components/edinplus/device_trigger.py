from __future__ import annotations

import voluptuous as vol

import logging

from .const import *

from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
    CONF_EVENT
)

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.device_automation.exceptions import DeviceNotFound
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, EDINPLUS_EVENT

TRIGGER_TYPES = NEWSTATE_TO_BUTTONEVENT.values()

INPUT_MODELS = {DEVCODE_TO_PRODNAME[2],DEVCODE_TO_PRODNAME[9]}

LOGGER = logging.getLogger(__name__)

# Set the trigger types to the different types of button event (imported from const.py)

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_DOMAIN): DOMAIN,
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)

async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device triggers for eDIN+ devices."""
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    # if device_entry is None:
    #     raise DeviceNotFound(f"Device ID {device_id} is not valid")
    if device_entry.model not in INPUT_MODELS:
        LOGGER.debug(f"[INVALID FOR INPUT] Device entry model is {device_entry.model}")
        return []
    LOGGER.debug(f"[VALID] Device entry model is {device_entry.model}")
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: CONF_EVENT,
            event_trigger.CONF_EVENT_TYPE: EDINPLUS_EVENT,
            event_trigger.CONF_EVENT_DATA: {
                CONF_TYPE: config[CONF_TYPE],
                CONF_DEVICE_ID: config[CONF_DEVICE_ID],
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )

# async def async_get_triggers(hass, device_id):
#     """Return a list of triggers."""
#     LOGGER.debug("Getting triggers")

#     device_registry = await hass.helpers.device_registry.async_get_registry()
#     device = device_registry.async_get(device_id)

#     triggers = []

#     # Determine which triggers are supported by this device_id ...

#     triggers.append({
#         # Required fields of TRIGGER_BASE_SCHEMA
#         CONF_PLATFORM: "device",
#         CONF_DOMAIN: "edinplus",
#         CONF_DEVICE_ID: device_id,
#         # Required fields of TRIGGER_SCHEMA
#         CONF_TYPE: "Press-on",
#     })

#     return triggers



# # This looks like it can mostly be kept stock
# async def async_attach_trigger(hass, config, action, trigger_info):
#     """Attach a trigger."""
#     event_config = event_trigger.TRIGGER_SCHEMA({
#         event_trigger.CONF_PLATFORM: CONF_EVENT,
#         event_trigger.CONF_EVENT_TYPE: "edinplus_event",
#         event_trigger.CONF_EVENT_DATA: {
#             CONF_DEVICE_ID: config[CONF_DEVICE_ID],
#             CONF_TYPE: config[CONF_TYPE],
#         },
#     }
#     return await event_trigger.async_attach_trigger(
#         hass, event_config, action, trigger_info, platform_type="device"
#     )