"""Constants for the eDIN+ HomeAssistant integration."""

# Devcodes, product names, status codes etc imported from Gateway Interface v2.0.3 (courtesy of Mode Lighting)

DOMAIN = "edinplus"

EDINPLUS_EVENT = f"{DOMAIN}_event" # Used for button presses (i.e. non-feedback based input from NPU)

DEVCODE_TO_PRODCODE = {
    1: "EVO-LCD-55",
    2: "EVO-SGP-xx",
    4: "EVO-RP-03-02",
    8: "EVS-xxx",
    9: "EVO-INT_CI_xx",
    12: "DIN-02-08",
    14: "DIN-03-04",
    15: "DIN-INT-00-08",
    16: "DIN-RP-05-04",
    17: "DIN-UBC-01-05",
    18: "DIN-DBM-00-08",
    24: "ECO_MULTISENSOR",
    144: "DIN-RP-05-04",
    145: "DIN-UBC-01-05",
}

DEVCODE_TO_PRODNAME = {
    1: "LCD Wall Plate",
    2: "2, 5 and 10 button Wall Plates, Coolbrium & Icon plates",
    4: "Evo 2-channel Relay Module",
    8: "All Evo Slave Packs",
    9: "Evo 4 & 8 channel Contact Input modules",
    12: "eDIN 2A 8 channel dimmer module",
    14: "eDIN 3A 4 channel dimmer module",
    15: "eDIN 8 channel IO module",
    16: "eDIN 5A 4 channel relay module",
    17: "eDIN Universal Ballast Control module",
    18: "eDIN 8 channel Configurable Output module",
    24: "eDIN Mk 1 Multisensor",
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
    4: "Bad Device Firmware",
    5: "No AC",
    6: "Too Hot",
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
    4: "System is configured to use features that are not present in current module firmware.",
    5: "Module uses mains AC and it does not detect any main AC power",
    6: "The module has detected that its internal temperature is above its maximum rated operating temperature.",
    10: "The module has detected there is a problem with the external load a channel is driving",
    20: "The module has detected that there is no PSU on its DALI bus.",
    21: "The DALI universe on this module does not contain any commissioning data.",
    22: "The module has detected that the actual DALI fixtures detected do not match with the commissioning data",
    25: "A DALI fixture on this channel is indicating a lamp failure condition",
    26: "A DALI fixture that is in the commissioning data is not present (is not responding)."
}