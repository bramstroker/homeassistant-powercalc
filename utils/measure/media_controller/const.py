from enum import Enum


class MediaControllerType(str, Enum):
    DUMMY = "dummy"
    HASS = "hass"
