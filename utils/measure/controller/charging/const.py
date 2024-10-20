from enum import Enum


class ChargingControllerType(str, Enum):
    DUMMY = "dummy"
    HASS = "hass"


class ChargingDeviceType(str, Enum):
    VACUUM_ROBOT = "vacuum robot"
    MOBILE_PHONE = "mobile phone"
