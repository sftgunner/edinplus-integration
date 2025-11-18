"""Config flow for the eDIN+ (by Mode Lighting) HomeAssistant integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.core import HomeAssistant

from .edinplus import edinplus_NPU_instance, EdinPlusConfig

# Import constants
from .const import DOMAIN, DEFAULT_TCP_PORT

_LOGGER = logging.getLogger(__name__)

# This is the schema that used to display the UI to the user.
# At the moment user is asked for the NPU address and TCP port.
# In future it could be useful to add support for username/password if setup on NPU
DATA_SCHEMA = vol.Schema({
    vol.Required("host"): str,
    vol.Optional("tcp_port", default=DEFAULT_TCP_PORT): int,
})

async def validate_input(hass: HomeAssistant, data: dict) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    
    # Validate the data can be used to set up a connection.

    # This is a simple example to show an error in the UI for a short hostname
    # The exceptions are defined at the end of this file, and are used in the
    # `async_step_user` method below.
    # This has been left from the example - could be changed to validate that it is a valid IP or DNS address
    if len(data["host"]) < 3:
        raise InvalidHost

    # Validate TCP port range
    tcp_port = data.get("tcp_port", DEFAULT_TCP_PORT)
    if not (1 <= tcp_port <= 65535):
        raise InvalidPort

    # NPU instance is initialised (see edinplus.py for more details)
    # This really ought to go through some verification to ensure the NPU is where it says it is, and supports TCP/HTTP without username/password
    # Have left example code below commented out for reference
    config = EdinPlusConfig(hostname=data["host"], tcp_port=tcp_port)
    hub = edinplus_NPU_instance(config)
    
    # # The dummy hub provides a `test_connection` method to ensure it's working
    # # as expected
    # result = await hub.test_connection()
    # if not result:
    #     # If there is an error, raise an exception to notify HA that there was a
    #     # problem. The UI will also show there was a problem
    #     raise CannotConnect

    # If you cannot connect:
    # throw CannotConnect
    # If the authentication is wrong:
    # InvalidAuth

    # Return info that you want to store in the config entry.
    # "Title" is what is displayed to the user for this hub device
    # It is stored internally in HA as part of the device config.
    # See `async_step_user` below for how this is used
    return {"title": data["host"]}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eDIN+."""

    VERSION = 1
    # Define connection class (defined in homeassistant/config_entries.py) as Local Polling
    # This should be changed to Local Push, as the TCP stream method means HA is informed by the NPU of any changes
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # This goes through the steps to take the user through the setup process.
        # Using this it is possible to update the UI and prompt for additional
        # information. This example provides a single form (built from `DATA_SCHEMA`),
        # and when that has some validated input, it calls `async_create_entry` to
        # actually create the HA config entry. Note the "title" value is returned by
        # `validate_input` above.
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                return self.async_create_entry(title=info["title"], data=user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidHost:
                # The error string is set here, and should be translated.
                # This example does not currently cover translations, see the
                # comments on `DATA_SCHEMA` for further details.
                # Set the error on the `host` field, not the entire form.
                errors["host"] = "cannot_connect"
            except InvalidPort:
                # Set the error on the `tcp_port` field
                errors["tcp_port"] = "invalid_port"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # If there is no user input or there were errors, show the form again, including any errors that were found with the input.
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""


class InvalidPort(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid TCP port."""