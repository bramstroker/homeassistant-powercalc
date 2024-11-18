from enum import Enum

MIN_MIRED = 150
MAX_MIRED = 500


class ColorMode(str, Enum):
    HS = "hs"
    COLOR_TEMP = "color_temp"
    BRIGHTNESS = "brightness"


class LightControllerType(str, Enum):
    DUMMY = "dummy"
    HASS = "hass"
    HUE = "hue"
