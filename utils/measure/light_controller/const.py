from enum import Enum

MODE_HS = "hs"
MODE_COLOR_TEMP = "color_temp"
MODE_BRIGHTNESS = "brightness"

MIN_MIRED = 150
MAX_MIRED = 500


class LightControllerType(str, Enum):
    DUMMY = "dummy"
    HASS = "hass"
    HUE = "hue"
