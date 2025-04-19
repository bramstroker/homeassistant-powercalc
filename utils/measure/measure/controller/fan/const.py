from enum import Enum


class FanControllerType(str, Enum):
    DUMMY = "dummy"
    HASS = "hass"
