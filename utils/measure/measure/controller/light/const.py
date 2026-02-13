from enum import StrEnum

MIN_MIRED = 150
MAX_MIRED = 500


class LutMode(StrEnum):
    HS = "hs"
    COLOR_TEMP = "color_temp"
    BRIGHTNESS = "brightness"
    EFFECT = "effect"
    WHITE = "white"


class LightControllerType(StrEnum):
    DUMMY = "dummy"
    HASS = "hass"
    HUE = "hue"
