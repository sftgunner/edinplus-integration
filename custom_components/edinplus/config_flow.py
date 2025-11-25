"""Config flow for the eDIN+ (by Mode Lighting) HomeAssistant integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.core import HomeAssistant

from .edinplus import edinplus_NPU_instance, EdinPlusConfig

# Import constants
from .const import *

_LOGGER = logging.getLogger(__name__)

# This is the schema that used to display the UI to the user.
# At the moment user is asked for the NPU address and TCP port.
# In future it could be useful to add support for username/password if setup on NPU
DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
        vol.Optional("tcp_port", default=DEFAULT_TCP_PORT): int,
        vol.Optional("use_chan_to_scn_proxy", default=True): bool,
        vol.Optional("auto_suggest_areas", default=True): bool,
        vol.Optional("keep_alive_interval", default=DEFAULT_KEEP_ALIVE_INTERVAL): int,
        vol.Optional("keep_alive_timeout", default=DEFAULT_KEEP_ALIVE_TIMEOUT): int,
        vol.Optional("systeminfo_interval", default=DEFAULT_SYSTEMINFO_INTERVAL): int,
        vol.Optional("reconnect_delay", default=DEFAULT_MIN_RECONNECT_DELAY): int,
        vol.Optional("max_reconnect_delay", default=DEFAULT_MAX_RECONNECT_DELAY): int,
    }
)

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
    config = EdinPlusConfig(
        hostname=data["host"],
        tcp_port=tcp_port,
        use_chan_to_scn_proxy=data.get("use_chan_to_scn_proxy", True),
        auto_suggest_areas=data.get("auto_suggest_areas", True),
        keep_alive_interval=data.get("keep_alive_interval", DEFAULT_KEEP_ALIVE_INTERVAL),
        keep_alive_timeout=data.get("keep_alive_timeout", DEFAULT_KEEP_ALIVE_TIMEOUT),
        systeminfo_interval=data.get("systeminfo_interval", DEFAULT_SYSTEMINFO_INTERVAL),
        reconnect_delay=data.get("reconnect_delay", DEFAULT_MIN_RECONNECT_DELAY),
        max_reconnect_delay=data.get("max_reconnect_delay", DEFAULT_MAX_RECONNECT_DELAY),
    )
    hub = edinplus_NPU_instance(config)
    
    # Test connection to ensure NPU is accessible
    _LOGGER.debug("Testing connection to NPU at %s", data["host"])
    result = await hub.async_test_connection()
    if not result:
        # If there is an error, raise an exception to notify HA that there was a
        # problem. The UI will also show there was a problem
        _LOGGER.error("Cannot connect to NPU at %s", data["host"])
        raise CannotConnect

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

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfigure step to adjust timing parameters.

        Allows users to change keep-alive interval/timeout, systeminfo interval,
        reconnect delay, and max reconnect delay.
        """

        # Attempt to retrieve the current entry being reconfigured
        entry = None
        entry_id = self.context.get("entry_id")
        if entry_id is not None:
            entry = self.hass.config_entries.async_get_entry(entry_id)
        # Fallback: first entry for this domain
        if entry is None:
            for e in self.hass.config_entries.async_entries(DOMAIN):
                entry = e
                break

        # Build schema with defaults from existing entry or constants
        defaults = {
            "keep_alive_interval": (entry.data.get("keep_alive_interval") if entry else DEFAULT_KEEP_ALIVE_INTERVAL),
            "keep_alive_timeout": (entry.data.get("keep_alive_timeout") if entry else DEFAULT_KEEP_ALIVE_TIMEOUT),
            "systeminfo_interval": (entry.data.get("systeminfo_interval") if entry else DEFAULT_SYSTEMINFO_INTERVAL),
            "reconnect_delay": (entry.data.get("reconnect_delay") if entry else DEFAULT_MIN_RECONNECT_DELAY),
            "max_reconnect_delay": (entry.data.get("max_reconnect_delay") if entry else DEFAULT_MAX_RECONNECT_DELAY),
        }

        schema = vol.Schema(
            {
                vol.Optional("keep_alive_interval", default=defaults["keep_alive_interval"]): int,
                vol.Optional("keep_alive_timeout", default=defaults["keep_alive_timeout"]): int,
                vol.Optional("systeminfo_interval", default=defaults["systeminfo_interval"]): int,
                vol.Optional("reconnect_delay", default=defaults["reconnect_delay"]): int,
                vol.Optional("max_reconnect_delay", default=defaults["max_reconnect_delay"]): int,
            }
        )

        errors: dict[str, str] = {}

        if user_input is not None:
            # Basic validation: ensure positive integers and coherent backoff
            try:
                vals: dict[str, int] = {}
                for key in ("keep_alive_interval", "keep_alive_timeout", "systeminfo_interval", "reconnect_delay", "max_reconnect_delay"):
                    value = int(user_input.get(key))
                    if value < 0:
                        errors[key] = "invalid_number"
                    vals[key] = value

                if not errors and vals["max_reconnect_delay"] < vals["reconnect_delay"]:
                    errors["max_reconnect_delay"] = "invalid_number"

                if not errors:
                    if entry is None:
                        errors["base"] = "no_entry"
                    else:
                        new_data = dict(entry.data)
                        for k, v in vals.items():
                            new_data[k] = v
                        # Persist changes to the existing entry
                        self.hass.config_entries.async_update_entry(entry, data=new_data)
                        # Reload entry so changes take effect immediately
                        await self.hass.config_entries.async_reload(entry.entry_id)
                        # Abort the flow with a success reason (no new entry created)
                        return self.async_abort(reason="reconfigure_successful")
            except Exception:
                # Avoid generic 'unknown'—set a stable error key
                errors["base"] = "update_failed"

        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""


class InvalidPort(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid TCP port."""