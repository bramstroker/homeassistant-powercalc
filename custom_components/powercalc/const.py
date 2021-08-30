"""The Hue Power constants."""

DOMAIN = "powercalc"
DOMAIN_CONFIG = "config"

DATA_CALCULATOR_FACTORY = "calculator_factory"

CONF_CALIBRATE = "calibrate"
CONF_CREATE_ENERGY_SENSOR = "create_energy_sensor"
CONF_CREATE_ENERGY_SENSORS = "create_energy_sensors"
CONF_CREATE_UTILITY_METERS = "create_utility_meters"
CONF_ENERGY_SENSOR_NAMING = "energy_sensor_naming"
CONF_ENTITY_NAME_PATTERN = "entity_name_pattern"
CONF_FIXED = "fixed"
CONF_LINEAR = "linear"
CONF_MODEL = "model"
CONF_MANUFACTURER = "manufacturer"
CONF_MODE = "mode"
CONF_MULTIPLY_FACTOR = "multiply_factor"
CONF_MULTIPLY_FACTOR_STANDBY = "multiply_factor_standby"
CONF_MIN_WATT = "min_watt"
CONF_MAX_WATT = "max_watt"
CONF_POWER_SENSOR_NAMING = "power_sensor_naming"
CONF_POWER = "power"
CONF_MIN_POWER = "min_power"
CONF_MAX_POWER = "max_power"
CONF_WATT = "watt"
CONF_STATES_POWER = "states_power"
CONF_STANDBY_USAGE = "standby_usage"
CONF_DISABLE_STANDBY_USAGE = "disable_standby_usage"
CONF_CUSTOM_MODEL_DIRECTORY = "custom_model_directory"
CONF_UTILITY_METER_TYPES = "utility_meter_types"

MODE_LUT = "lut"
MODE_LINEAR = "linear"
MODE_FIXED = "fixed"
CALCULATION_MODES = [
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT,
]

MANUFACTURER_DIRECTORY_MAPPING = {
    "IKEA of Sweden": "ikea",
    "Feibit Inc co.  ": "jiawen",
    "LEDVANCE": "ledvance",
    "MLI": "mueller-licht",
    "OSRAM": "osram",
    "Signify Netherlands B.V.": "signify",
}

MODEL_DIRECTORY_MAPPING = {
    "IKEA of Sweden": {
        "TRADFRI bulb E14 WS opal 400lm": "LED1536G5",
        "TRADFRI bulb GU10 WS 400lm": "LED1537R6",
        "TRADFRI bulb E27 WS opal 980lm": "LED1545G12",
        "TRADFRI bulb E27 WS clear 950lm": "LED1546G12",
        "TRADFRI bulb E27 opal 1000lm": "LED1623G12",
        "TRADFRI bulb E27 CWS opal 600lm": "LED1624G9",
        "TRADFRI bulb E14 W op/ch 400lm": "LED1649C5",
        "TRADFRI bulb GU10 W 400lm": "LED1650R5",
        "TRADFRI bulb E27 WS opal 1000lm": "LED1732G11",
    }
}
