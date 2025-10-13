from enum import Enum


class ChargingControllerType(str, Enum):
    DUMMY = "dummy"
    HASS = "hass"


class ChargingDeviceType(str, Enum):
    VACUUM_ROBOT = "vacuum_robot"
    LAWN_MOWER_ROBOT = "lawn_mower_robot"


class BatteryLevelSourceType(str, Enum):
    ATTRIBUTE = "attribute"
    ENTITY = "entity"


QUESTION_BATTERY_LEVEL_ATTRIBUTE = "battery_level_attribute"
QUESTION_BATTERY_LEVEL_ENTITY = "battery_level_entity"
QUESTION_BATTERY_LEVEL_SOURCE_TYPE = "battery_level_source_type"
