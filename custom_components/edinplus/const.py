"""Constants for the eDIN+ HomeAssistant integration."""

DOMAIN = "edinplus"

# DEFAULTS
DEFAULT_TCP_PORT = 26
DEFAULT_KEEP_ALIVE_INTERVAL = 10    # seconds;  How often to poll system to check that the connection is still alive (NB nominal cycle time = interval + timeout); NPU drops the TCP connection from its side after ~3600s idle
DEFAULT_KEEP_ALIVE_TIMEOUT = 2      # seconds;  How long we wait for a keep-alive ack from the NPU (!OK; response to $OK;) before evaluating whether keep-alive failed
DEFAULT_MAX_RETRY_ATTEMPTS = 5      # attempts; How many times we will retry keep-alive before assuming connection is lost and attempting TCP reconnect

DEFAULT_SYSTEMINFO_INTERVAL = 300   # seconds;  How often to poll system info from NPU to check whether config has changed (and there might be new devices to discover)
DEFAULT_MIN_RECONNECT_DELAY = 2     # seconds;  
DEFAULT_MAX_RECONNECT_DELAY = 60    # seconds;

EDINPLUS_EVENT = f"{DOMAIN}_event" # Used for button presses (i.e. non-feedback based input from NPU)

# Devcodes, product names, status codes etc imported from Gateway Interface v2.0.3 (courtesy of Mode Lighting)

DEVCODE_TO_PRODCODE = {
    1: "EVO-LCD-55",
    2: "EVO-SGP-xx",
    4: "EVO-RP-03-02",
    8: "EVS-xxx",
    9: "EVO-INT_CI_xx",
    12: "DIN-02-08",
    13: "DIN-03-04-TE",
    14: "DIN-03-04",
    15: "DIN-INT-00-08",
    16: "DIN-RP-05-04",
    17: "DIN-UBC-01-05",
    18: "DIN-DBM-00-08",
    19: "DIN-DCM-xxx",
    21: "DIN-RP-00-xx",
    24: "ECO_MULTISENSOR",
    30: "MBUS-SPLIT",
    144: "DIN-RP-05-04",
    145: "DIN-UBC-01-05",
}

DEVCODE_TO_PRODNAME = {
    1: "LCD Wall Plate",
    2: "2, 5 and 10 button Wall Plates, Coolbrium & Icon plates",
    4: "Evo 2-channel Relay Module",
    8: "All Legacy Evo Slave Packs",
    9: "Evo 4 & 8 channel Contact Input modules",
    12: "eDIN 2A 8 channel leading edge dimmer module",
    13: "eDIN 3A 4 channel trailing edge dimmer module",
    14: "eDIN 3A 4 channel leading edge dimmer module",
    15: "eDIN 8 channel IO module",
    16: "eDIN 5A 4 channel relay module",
    17: "eDIN Universal Ballast Control module",
    18: "eDIN 8 channel Configurable Output module",
    19: "All eDIN Dimmer Packs",
    21: "All eDIN Rotary switch wall plates",
    24: "eDIN Multi-sensor (both Mk1 and Mk2)",
    30: "MBus splitter module",
    144: "eDIN 5A 4 channel mains sync relay module",
    145: "eDIN Universal Ballast Control 2 module",
}

NEWSTATE_TO_BUTTONEVENT = {
    0: "Release-off",
    1: "Press-on",
    2: "Hold-on",
    5: "Short-press",
    6: "Hold-off"
}

STATUSCODE_TO_SUMMARY = {
    0: "Status Ok",
    2: "Device missing",
    3: "Channel Errors",
    4: "Bad Device Firmware",
    5: "No AC",
    6: "Too Hot",
    7: "Override Active",
    8: "Internal Failure",
    9: "DALI Fixture Errors",
    10: "Channel Load Failure",
    20: "No DALI PSU",
    21: "No DALI Commissioning Data",
    22: "DALI Commissioning problem",
    25: "DALI Lamp failure",
    26: "DALI missing ballast"
}

STATUSCODE_TO_DESC = {
    0: "No Errors",
    2: "Device or Module is not responding to MBus messages.",
    3: "Module has errors on at least one specific channel – see the individual channel for details of the error",
    4: "System is configured to use features that are not present in current module firmware.",
    5: "Module uses mains AC and it does not detect any main AC power",
    6: "The module has detected that its internal temperature is above its maximum rated operating temperature.",
    7: "The channel has been manually set to override mode and is no longer controlled by the system",
    8: "The channel or module has detected some sort of hardware failure internally",
    9: "There are fixtures on this DALI channel that are reporting errors – see the individual DALI fixtures for details of the error",
    10: "The module has detected there is a problem with the external load a channel is driving",
    20: "The module has detected that there is no PSU on its DALI bus.",
    21: "The DALI universe on this module does not contain any commissioning data.",
    22: "The module has detected that the actual DALI fixtures detected do not match with the commissioning data",
    25: "A DALI fixture on this channel is indicating a lamp failure condition",
    26: "A DALI fixture that is in the commissioning data is not present (is not responding)."
}