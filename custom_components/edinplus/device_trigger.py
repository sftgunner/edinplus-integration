from __future__ import annotations

from .const import *

from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_TYPE,
)

# Set the trigger types to the different types of button event (imported from const.py)
TRIGGER_TYPES = NEWSTATE_TO_BUTTONEVENT

TRIGGER_SCHEMA = TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)