from enum import Enum


class ChargingControllerType(str, Enum):
    DUMMY = "dummy"
    HASS = "hass"


class ChargingDeviceType(str, Enum):
    VACUUM_ROBOT = "vacuum robot"


QUESTION_BATTERY_LEVEL_ATTRIBUTE = "battery_level_attribute"
