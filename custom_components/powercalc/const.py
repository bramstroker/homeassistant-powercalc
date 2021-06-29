"""The Hue Power constants."""

DOMAIN = "powercalc"

DATA_CALCULATOR_FACTORY = "calculator_factory"

CONF_CALIBRATE = "calibrate"
CONF_FIXED = "fixed"
CONF_LINEAR = "linear"
CONF_MODEL = "model"
CONF_MANUFACTURER = "manufacturer"
CONF_MODE = "mode"
CONF_MIN_WATT = "min_watt"
CONF_MAX_WATT = "max_watt"
CONF_POWER = "power"
CONF_MIN_POWER = "min_power"
CONF_MAX_POWER = "max_power"
CONF_WATT = "watt"
CONF_STATES_POWER = "states_power"
CONF_STANDBY_USAGE = "standby_usage"
CONF_DISABLE_STANDBY_USAGE = "disable_standby_usage"
CONF_CUSTOM_MODEL_DIRECTORY = "custom_model_directory"

MODE_LUT = "lut"
MODE_LINEAR = "linear"
MODE_FIXED = "fixed"

MANUFACTURER_DIRECTORY_MAPPING = {
    "IKEA of Sweden": "ikea",
    "OSRAM": "osram",
    "Signify Netherlands B.V.": "signify",
}

MODEL_DIRECTORY_MAPPING = {
    "IKEA of Sweden": {
        "TRADFRI bulb E27 opal 1000lm": "LED1623G12",
        "TRADFRI bulb E14 W op/ch 400lm": "LED1649C5",
        "TRADFRI bulb GU10 W 400lm": "LED1650R5",
    }
}
