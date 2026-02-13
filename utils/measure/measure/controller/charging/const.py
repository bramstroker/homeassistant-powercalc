from enum import StrEnum


class ChargingControllerType(StrEnum):
    DUMMY = "dummy"
    HASS = "hass"


class ChargingDeviceType(StrEnum):
    VACUUM_ROBOT = "vacuum_robot"
    LAWN_MOWER_ROBOT = "lawn_mower_robot"


class BatteryLevelSourceType(StrEnum):
    ATTRIBUTE = "attribute"
    ENTITY = "entity"


QUESTION_BATTERY_LEVEL_ATTRIBUTE = "battery_level_attribute"
QUESTION_BATTERY_LEVEL_ENTITY = "battery_level_entity"
QUESTION_BATTERY_LEVEL_SOURCE_TYPE = "battery_level_source_type"
