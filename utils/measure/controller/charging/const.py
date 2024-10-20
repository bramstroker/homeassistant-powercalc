from enum import Enum


class ChargingControllerType(str, Enum):
    DUMMY = "dummy"
    HASS = "hass"


class ChargingDeviceType(str, Enum):
    VACUUM = "vacuum robot"
    MOBILE_PHONE = "mobile phone"
