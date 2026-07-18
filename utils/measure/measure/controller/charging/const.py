from enum import StrEnum


class ChargingControllerType(StrEnum):
    DUMMY = "dummy"
    HASS = "hass"


class ChargingDeviceType(StrEnum):
    VACUUM_ROBOT = "vacuum_robot"
    LAWN_MOWER_ROBOT = "lawn_mower_robot"


ATTR_BATTERY_LEVEL = "battery_level"
