"""The Powercalc constants."""

DOMAIN = "powercalc"
DOMAIN_CONFIG = "config"

DATA_CALCULATOR_FACTORY = "calculator_factory"
DATA_CONFIGURED_ENTITIES = "configured_entities"
DATA_DISCOVERED_ENTITIES = "discovered_entities"

DUMMY_ENTITY_ID = "dummy"

CONF_AREA = "area"
CONF_CALIBRATE = "calibrate"
CONF_CREATE_GROUP = "create_group"
CONF_CREATE_ENERGY_SENSOR = "create_energy_sensor"
CONF_CREATE_ENERGY_SENSORS = "create_energy_sensors"
CONF_CREATE_UTILITY_METERS = "create_utility_meters"
CONF_DAILY_FIXED_ENERGY = "daily_fixed_energy"
CONF_ENABLE_AUTODISCOVERY = "enable_autodiscovery"
CONF_ENERGY_SENSOR_NAMING = "energy_sensor_naming"
CONF_FIXED = "fixed"
CONF_GROUP = "group"
CONF_INCLUDE = "include"
CONF_LINEAR = "linear"
CONF_MODEL = "model"
CONF_MANUFACTURER = "manufacturer"
CONF_MODE = "mode"
CONF_MULTIPLY_FACTOR = "multiply_factor"
CONF_MULTIPLY_FACTOR_STANDBY = "multiply_factor_standby"
CONF_MIN_WATT = "min_watt"
CONF_MAX_WATT = "max_watt"
CONF_POWER_FACTOR = "power_factor"
CONF_POWER_SENSOR_NAMING = "power_sensor_naming"
CONF_POWER = "power"
CONF_MIN_POWER = "min_power"
CONF_MAX_POWER = "max_power"
CONF_ON_TIME = "on_time"
CONF_UPDATE_FREQUENCY = "update_frequency"
CONF_VALUE = "value"
CONF_VOLTAGE = "voltage"
CONF_WATT = "watt"
CONF_WLED = "wled"
CONF_STATES_POWER = "states_power"
CONF_STANDBY_POWER = "standby_power"
CONF_DISABLE_STANDBY_POWER = "disable_standby_power"
CONF_STANDBY_USAGE = "standby_usage"
CONF_DISABLE_STANDBY_USAGE = "disable_standby_usage"
CONF_CUSTOM_MODEL_DIRECTORY = "custom_model_directory"
CONF_UTILITY_METER_OFFSET = "utility_meter_offset"
CONF_UTILITY_METER_TYPES = "utility_meter_types"

DISCOVERY_SOURCE_ENTITY = "source_entity"
DISCOVERY_LIGHT_MODEL = "light_model"

ATTR_CALCULATION_MODE = "calculation_mode"
ATTR_ENTITIES = "entities"
ATTR_INTEGRATION = "integration"
ATTR_IS_GROUP = "is_group"
ATTR_SOURCE_ENTITY = "source_entity"
ATTR_SOURCE_DOMAIN = "source_domain"

MODE_DAILY_FIXED_ENERGY = "daily_fixed_energy"
MODE_LUT = "lut"
MODE_LINEAR = "linear"
MODE_FIXED = "fixed"
MODE_WLED = "wled"
CALCULATION_MODES = [
    MODE_DAILY_FIXED_ENERGY,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT,
    MODE_WLED,
]

MANUFACTURER_DIRECTORY_MAPPING = {
    "IKEA of Sweden": "ikea",
    "Feibit Inc co.  ": "jiawen",
    "LEDVANCE": "ledvance",
    "MLI": "mueller-licht",
    "OSRAM": "osram",
    "Signify Netherlands B.V.": "signify",
    "Aqara": "aqara",
}

MANUFACTURER_ALIASES = {
    "Philips": "Signify Netherlands B.V.",
    "IKEA": "Ikea of Sweden",
    "Xiaomi": "Aqara",
    "LUMI": "Aqara",
}

MODEL_DIRECTORY_MAPPING = {
    "IKEA of Sweden": {
        "TRADFRI bulb E14 WS opal 400lm": "LED1536G5",
        "TRADFRI bulb GU10 WS 400lm": "LED1537R6",
        "TRADFRI bulb E27 WS opal 980lm": "LED1545G12",
        "TRADFRI bulb E27 WS clear 950lm": "LED1546G12",
        "TRADFRI bulb E27 opal 1000lm": "LED1623G12",
        "TRADFRI bulb E14 W op/ch 400lm": "LED1649C5",
        "TRADFRI bulb GU10 W 400lm": "LED1650R5",
        "TRADFRI bulb E27 WS opal 1000lm": "LED1732G11",
        "TRADFRI bulb GU10 WW 400lm": "LED1837R5",
        "TRADFRI bulb E27 WW 806lm": "LED1836G9",
    },
    "Signify Netherlands B.V.": {
        "440400982841": "LCT024",
        "8718696449691": "LWB010",
        "3417711P6": "LTW017",
        "3418931P6": "LTC012",
        "3261030P6": "LTC001",
        "3261031P6": "LTC001",
        "3261048P6": "LTC001",
    },
}
