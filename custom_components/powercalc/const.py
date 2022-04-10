"""The Powercalc constants."""

from datetime import timedelta

from homeassistant.components.utility_meter.const import DAILY, MONTHLY, WEEKLY

DOMAIN = "powercalc"
DOMAIN_CONFIG = "config"

DATA_CALCULATOR_FACTORY = "calculator_factory"
DATA_CONFIGURED_ENTITIES = "configured_entities"
DATA_DISCOVERED_ENTITIES = "discovered_entities"
DATA_DOMAIN_ENTITIES = "domain_entities"

DUMMY_ENTITY_ID = "dummy"

CONF_AREA = "area"
CONF_CALIBRATE = "calibrate"
CONF_CREATE_GROUP = "create_group"
CONF_CREATE_DOMAIN_GROUPS = "create_domain_groups"
CONF_CREATE_ENERGY_SENSOR = "create_energy_sensor"
CONF_CREATE_ENERGY_SENSORS = "create_energy_sensors"
CONF_CREATE_UTILITY_METERS = "create_utility_meters"
CONF_DAILY_FIXED_ENERGY = "daily_fixed_energy"
CONF_ENABLE_AUTODISCOVERY = "enable_autodiscovery"
CONF_ENERGY_INTEGRATION_METHOD = "energy_integration_method"
CONF_ENERGY_SENSOR_CATEGORY = "energy_sensor_category"
CONF_ENERGY_SENSOR_NAMING = "energy_sensor_naming"
CONF_ENERGY_SENSOR_PRECISION = "energy_sensor_precision"
CONF_FIXED = "fixed"
CONF_GROUP = "group"
CONF_GAMMA_CURVE = "gamma_curve"
CONF_IGNORE_UNAVAILABLE_STATE = "ignore_unavailable_state"
CONF_INCLUDE = "include"
CONF_LINEAR = "linear"
CONF_MODEL = "model"
CONF_MANUFACTURER = "manufacturer"
CONF_MODE = "mode"
CONF_MULTIPLY_FACTOR = "multiply_factor"
CONF_MULTIPLY_FACTOR_STANDBY = "multiply_factor_standby"
CONF_POWER_FACTOR = "power_factor"
CONF_POWER_SENSOR_CATEGORY = "power_sensor_category"
CONF_POWER_SENSOR_NAMING = "power_sensor_naming"
CONF_POWER_SENSOR_PRECISION = "power_sensor_precision"
CONF_POWER = "power"
CONF_POWER_SENSOR_ID = "power_sensor_id"
CONF_MIN_POWER = "min_power"
CONF_MAX_POWER = "max_power"
CONF_ON_TIME = "on_time"
CONF_TEMPLATE = "template"
CONF_UPDATE_FREQUENCY = "update_frequency"
CONF_VALUE = "value"
CONF_VOLTAGE = "voltage"
CONF_WLED = "wled"
CONF_STATES_POWER = "states_power"
CONF_STANDBY_POWER = "standby_power"
CONF_DISABLE_STANDBY_POWER = "disable_standby_power"
CONF_CUSTOM_MODEL_DIRECTORY = "custom_model_directory"
CONF_UTILITY_METER_OFFSET = "utility_meter_offset"
CONF_UTILITY_METER_TYPES = "utility_meter_types"
CONF_UTILITY_METER_TARIFFS = "utility_meter_tariffs"

# Redefine constants from integration component.
# Has been refactored in HA 2022.4, we need to support older HA versions as well.
ENERGY_INTEGRATION_METHOD_LEFT = "left"
ENERGY_INTEGRATION_METHOD_RIGHT = "right"
ENERGY_INTEGRATION_METHOD_TRAPEZODIAL = "trapezoidal"
ENERGY_INTEGRATION_METHODS = [
    ENERGY_INTEGRATION_METHOD_LEFT,
    ENERGY_INTEGRATION_METHOD_RIGHT,
    ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
]

ENTITY_CATEGORY_CONFIG = "config"
ENTITY_CATEGORY_DIAGNOSTIC = "diagnostic"
ENTITY_CATEGORY_NONE = None
ENTITY_CATEGORY_SYSTEM = "system"
ENTITY_CATEGORIES = [
    ENTITY_CATEGORY_CONFIG,
    ENTITY_CATEGORY_DIAGNOSTIC,
    ENTITY_CATEGORY_NONE,
    ENTITY_CATEGORY_SYSTEM,
]

DEFAULT_SCAN_INTERVAL = timedelta(minutes=10)
DEFAULT_POWER_NAME_PATTERN = "{} power"
DEFAULT_POWER_SENSOR_PRECISION = 2
DEFAULT_ENERGY_INTEGRATION_METHOD = ENERGY_INTEGRATION_METHOD_TRAPEZODIAL
DEFAULT_ENERGY_NAME_PATTERN = "{} energy"
DEFAULT_ENERGY_SENSOR_PRECISION = 4
DEFAULT_ENTITY_CATEGORY = ENTITY_CATEGORY_NONE
DEFAULT_UTILITY_METER_TYPES = [DAILY, WEEKLY, MONTHLY]

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
    "Lexman": "lexman",
}

MANUFACTURER_ALIASES = {
    "Philips": "Signify Netherlands B.V.",
    "IKEA": "IKEA of Sweden",
    "Xiaomi": "Aqara",
    "LUMI": "Aqara",
    "ADEO": "Lexman",
}

MODEL_DIRECTORY_MAPPING = {
    "IKEA of Sweden": {
        "FLOALT panel WS 30x30": "L1527",
        "FLOALT panel WS 60x60": "L1529",
        "TRADFRI bulb E14 WS opal 400lm": "LED1536G5",
        "TRADFRI bulb GU10 WS 400lm": "LED1537R6",
        "TRADFRI bulb E27 WS opal 980lm": "LED1545G12",
        "TRADFRI bulb E27 WS clear 950lm": "LED1546G12",
        "TRADFRI bulb E27 opal 1000lm": "LED1623G12",
        "TRADFRI bulb E27 W opal 1000lm": "LED1623G12",
        "TRADFRI bulb E14 CWS opal 600lm": "LED1624G9",
        "TRADFRI bulb E26 CWS opal 600lm": "LED1624G9",
        "TRADFRI bulb E27 CWS opal 600lm": "LED1624G9",
        "TRADFRI bulb E14 W op/ch 400lm": "LED1649C5",
        "TRADFRI bulb GU10 W 400lm": "LED1650R5",
        "TRADFRI bulb E27 WS opal 1000lm": "LED1732G11",
        "TRADFRI bulb E14 WS opal 600lm": "LED1733G7",
        "TRADFRI bulb E27 WS clear 806lm": "LED1736G9",
        "TRADFRI bulb E14 WS opal 600lm": "LED1738G7",
        "TRADFRI bulb E14 WS 470lm": "LED1835C6",
        "TRADFRI bulb E27 WW 806lm": "LED1836G9",
        "TRADFRI bulb E27 WW clear 250lm": "LED1842G3",
        "TRADFRI bulb GU10 WW 400lm": "LED1837R5",
        "TRADFRI bulb GU10 CWS 345lm": "LED1923R5",
        "TRADFRI bulb E27 CWS 806lm": "LED1924G9",
        "TRADFRI bulb E14 CWS 470lm": "LED1925G6",
        "TRADFRIbulbE14WScandleopal470lm": "LED1949C5",
        "TRADFRIbulbE14WSglobeopal470lm": "LED2002G5",
        "TRADFRIbulbE27WSglobeopal1055lm": "LED2003G10",
        "TTRADFRIbulbGU10WS345lm": "LED2005R5",
        "TRADFRI bulb GU10 WW 345lm": "LED2005R5",
        "LEPTITER Recessed spot light": "T1820",
    },
    "Signify Netherlands B.V.": {
        "9290022166": "LCA001",
        "929003053401": "LCA001",
        "929001953101": "LCG002",
        "9290012573A": "LCT015",
        "440400982841": "LCT024",
        "7602031P7": "LCT026",
        "9290022169": "LTA001",
        "3261030P6": "LTC001",
        "3261031P6": "LTC001",
        "3261048P6": "LTC001",
        "3418931P6": "LTC012",
        "3417711P6": "LTW017",
        "8718699673147": "LWA001",
        "8718696449691": "LWB010",
        "9290024406": "LWU001",
        "9290011370B": "LWF001",
        "8719514328242": "LTA004",
        "8718699703424": "LCL001",
        "8718699671211": "LWE002",
        "9290020399": "LWE002",
    },
}
