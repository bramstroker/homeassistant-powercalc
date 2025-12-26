"""The Powercalc constants."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from homeassistant.components import cover, device_tracker
from homeassistant.components.utility_meter.const import DAILY, MONTHLY, WEEKLY
from homeassistant.const import (
    STATE_CLOSED,
    STATE_NOT_HOME,
    STATE_OFF,
    STATE_OPEN,
    STATE_STANDBY,
    STATE_UNAVAILABLE,
    EntityCategory,
)

MIN_HA_VERSION = "2025.1"

DOMAIN = "powercalc"
DOMAIN_CONFIG = "config"

DATA_CONFIGURED_ENTITIES = "configured_entities"
DATA_DISCOVERY_MANAGER = "discovery_manager"
DATA_DOMAIN_ENTITIES = "domain_entities"
DATA_ENTITIES = "entities"
DATA_GROUP_ENTITIES = "group_entities"
DATA_USED_UNIQUE_IDS = "used_unique_ids"
DATA_STANDBY_POWER_SENSORS = "standby_power_sensors"
DATA_ANALYTICS = "analytics"
DATA_ANALYTICS_SEEN_ENTRIES = "analytics_seen_entries"
DATA_POWER_PROFILES: Literal["power_profiles"] = "power_profiles"
DATA_SENSOR_TYPES: Literal["sensor_types"] = "sensor_types"
DATA_CONFIG_TYPES: Literal["config_types"] = "config_types"
DATA_SOURCE_DOMAINS: Literal["source_domains"] = "source_domains"
DATA_GROUP_TYPES: Literal["group_types"] = "group_types"
DATA_STRATEGIES: Literal["strategies"] = "strategies"
DATA_GROUP_SIZES: Literal["group_sizes"] = "group_sizes"
DATA_HAS_GROUP_INCLUDE: Literal["has_group_include"] = "has_group_include"

ENTRY_DATA_ENERGY_ENTITY = "_energy_entity"
ENTRY_DATA_POWER_ENTITY = "_power_entity"
ENTRY_GLOBAL_CONFIG_UNIQUE_ID = "powercalc_global_configuration"

DUMMY_ENTITY_ID = "sensor.dummy"

CONF_ALL = "all"
CONF_AND = "and"
CONF_ENABLE_ANALYTICS = "enable_analytics"
CONF_AREA = "area"
CONF_AUTOSTART = "autostart"
CONF_AVAILABILITY_ENTITY = "availability_entity"
CONF_CALCULATION_ENABLED_CONDITION = "calculation_enabled_condition"
CONF_CALIBRATE = "calibrate"
CONF_CATEGORY = "category"
CONF_COMPOSITE = "composite"
CONF_CREATE_DOMAIN_GROUPS = "create_domain_groups"
CONF_CREATE_ENERGY_SENSOR = "create_energy_sensor"
CONF_CREATE_ENERGY_SENSORS = "create_energy_sensors"
CONF_CREATE_GROUP = "create_group"
CONF_CREATE_STANDBY_GROUP = "create_standby_group"
CONF_CREATE_UTILITY_METERS = "create_utility_meters"
CONF_CUSTOM_MODEL_DIRECTORY = "custom_model_directory"
CONF_DAILY_FIXED_ENERGY = "daily_fixed_energy"
CONF_DELAY = "delay"
CONF_DISABLE_EXTENDED_ATTRIBUTES = "disable_extended_attributes"
CONF_DISABLE_LIBRARY_DOWNLOAD = "disable_library_download"
CONF_DISABLE_STANDBY_POWER = "disable_standby_power"
CONF_DISCOVERY: str = "discovery"
CONF_EXCLUDE_DEVICE_TYPES = "exclude_device_types"
CONF_EXCLUDE_SELF_USAGE = "exclude_self_usage"

# Deprecated configuration keys
CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED = "discovery_exclude_device_types"
CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED = "discovery_exclude_self_usage"
CONF_ENABLE_AUTODISCOVERY_DEPRECATED = "enable_autodiscovery"
CONF_GROUP_UPDATE_INTERVAL_DEPRECATED = "group_update_interval"
CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED = "force_update_frequency"

CONF_ENERGY_INTEGRATION_METHOD = "energy_integration_method"
CONF_ENERGY_SENSOR_CATEGORY = "energy_sensor_category"
CONF_ENERGY_SENSOR_FRIENDLY_NAMING = "energy_sensor_friendly_naming"
CONF_ENERGY_SENSOR_ID = "energy_sensor_id"
CONF_ENERGY_SENSOR_NAMING = "energy_sensor_naming"
CONF_ENERGY_SENSOR_PRECISION = "energy_sensor_precision"
CONF_ENERGY_SENSOR_UNIT_PREFIX = "energy_sensor_unit_prefix"
CONF_ENERGY_UPDATE_INTERVAL = "energy_update_interval"
CONF_ENERGY_FILTER_OUTLIER_ENABLED = "energy_filter_outlier_enabled"
CONF_ENERGY_FILTER_OUTLIER_MAX = "energy_filter_outlier_max_step"
CONF_EXCLUDE_ENTITIES = "exclude_entities"
CONF_FILTER = "filter"
CONF_FIXED = "fixed"
CONF_FLOOR = "floor"
CONF_FORCE_CALCULATE_GROUP_ENERGY = "force_calculate_group_energy"
CONF_FORCE_ENERGY_SENSOR_CREATION = "force_energy_sensor_creation"
CONF_GAMMA_CURVE = "gamma_curve"
CONF_GROUP = "group"
CONF_GROUP_ENERGY_ENTITIES = "group_energy_entities"
CONF_GROUP_ENERGY_START_AT_ZERO = "group_energy_start_at_zero"
CONF_GROUP_ENERGY_UPDATE_INTERVAL = "group_energy_update_interval"
CONF_GROUP_MEMBER_DEVICES = "group_member_devices"
CONF_GROUP_MEMBER_SENSORS = "group_member_sensors"
CONF_GROUP_POWER_ENTITIES = "group_power_entities"
CONF_GROUP_POWER_UPDATE_INTERVAL = "group_power_update_interval"
CONF_GROUP_TRACKED_AUTO = "group_tracked_auto"
CONF_GROUP_TRACKED_POWER_ENTITIES = "group_tracked_entities"
CONF_GROUP_TYPE = "group_type"
CONF_HIDE_MEMBERS = "hide_members"
CONF_IGNORE_UNAVAILABLE_STATE = "ignore_unavailable_state"
CONF_INCLUDE = "include"
CONF_INCLUDE_NON_POWERCALC_SENSORS = "include_non_powercalc_sensors"
CONF_LABEL = "label"
CONF_LINEAR = "linear"
CONF_MAIN_POWER_SENSOR = "main_power_sensor"
CONF_MANUFACTURER = "manufacturer"
CONF_MAX_POWER = "max_power"
CONF_MIN_POWER = "min_power"
CONF_MODEL = "model"
CONF_MODE = "mode"
CONF_MULTI_SWITCH = "multi_switch"
CONF_MULTIPLY_FACTOR = "multiply_factor"
CONF_MULTIPLY_FACTOR_STANDBY = "multiply_factor_standby"
CONF_NEW_GROUP = "new_group"
CONF_NOT = "not"
CONF_ON_TIME = "on_time"
CONF_OR = "or"
CONF_PLAYBOOK = "playbook"
CONF_PLAYBOOKS = "playbooks"
CONF_POWER = "power"
CONF_POWER_FACTOR = "power_factor"
CONF_POWER_OFF = "power_off"
CONF_POWER_SENSOR_CATEGORY = "power_sensor_category"
CONF_POWER_SENSOR_FRIENDLY_NAMING = "power_sensor_friendly_naming"
CONF_POWER_SENSOR_ID = "power_sensor_id"
CONF_POWER_SENSOR_NAMING = "power_sensor_naming"
CONF_POWER_SENSOR_PRECISION = "power_sensor_precision"
CONF_POWER_TEMPLATE = "power_template"
CONF_REPEAT = "repeat"
CONF_SELF_USAGE_INCLUDED = "self_usage_included"
CONF_SENSOR_TYPE = "sensor_type"
CONF_SENSORS = "sensors"
CONF_SLEEP_POWER = "sleep_power"
CONF_STANDBY_POWER = "standby_power"
CONF_START_TIME = "start_time"
CONF_STATES_POWER = "states_power"
CONF_STATE_TRIGGER = "state_trigger"
CONF_STATES_TRIGGER = "states_trigger"
CONF_STRATEGIES = "strategies"
CONF_SUB_GROUPS = "sub_groups"
CONF_SUB_PROFILE = "sub_profile"
CONF_SUBTRACT_ENTITIES = "subtract_entities"
CONF_TEMPLATE = "template"
CONF_UNAVAILABLE_POWER = "unavailable_power"
CONF_UPDATE_FREQUENCY = "update_frequency"
CONF_UTILITY_METER_NET_CONSUMPTION = "utility_meter_net_consumption"
CONF_UTILITY_METER_OFFSET = "utility_meter_offset"
CONF_UTILITY_METER_TARIFFS = "utility_meter_tariffs"
CONF_UTILITY_METER_TYPES = "utility_meter_types"
CONF_VALUE = "value"
CONF_VALUE_TEMPLATE = "value_template"
CONF_VARIABLES = "variables"
CONF_VOLTAGE = "voltage"
CONF_WILDCARD = "wildcard"
CONF_WLED = "wled"

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


class UnitPrefix(StrEnum):
    """Allowed unit prefixes."""

    NONE = "none"
    KILO = "k"
    MEGA = "M"
    GIGA = "G"
    TERA = "T"


ENTITY_CATEGORIES = [
    EntityCategory.CONFIG,
    EntityCategory.DIAGNOSTIC,
    None,
]

DEFAULT_GROUP_POWER_UPDATE_INTERVAL = 2
DEFAULT_GROUP_ENERGY_UPDATE_INTERVAL = 60
DEFAULT_POWER_NAME_PATTERN = "{} power"
DEFAULT_POWER_SENSOR_PRECISION = 2
DEFAULT_ENERGY_UPDATE_INTERVAL = 600
DEFAULT_ENERGY_INTEGRATION_METHOD = ENERGY_INTEGRATION_METHOD_LEFT
DEFAULT_ENERGY_NAME_PATTERN = "{} energy"
DEFAULT_ENERGY_SENSOR_PRECISION = 4
DEFAULT_ENERGY_UNIT_PREFIX = UnitPrefix.KILO
DEFAULT_ENTITY_CATEGORY: str | None = None
DEFAULT_UTILITY_METER_TYPES = [DAILY, WEEKLY, MONTHLY]

DISCOVERY_SOURCE_ENTITY = "source_entity"
DISCOVERY_POWER_PROFILES = "power_profiles"
DISCOVERY_TYPE = "discovery_type"

LIBRARY_URL = "https://library.powercalc.nl"
API_URL = "https://api.powercalc.nl"

MANUFACTURER_WLED = "WLED"

ATTR_CALCULATION_MODE = "calculation_mode"
ATTR_ENERGY_SENSOR_ENTITY_ID = "energy_sensor_entity_id"
ATTR_ENTITIES = "entities"
ATTR_INTEGRATION = "integration"
ATTR_IS_GROUP = "is_group"
ATTR_SOURCE_ENTITY = "source_entity"
ATTR_SOURCE_DOMAIN = "source_domain"

SERVICE_ACTIVATE_PLAYBOOK = "activate_playbook"
SERVICE_CALIBRATE_UTILITY_METER = "calibrate_utility_meter"
SERVICE_CALIBRATE_ENERGY = "calibrate_energy"
SERVICE_CHANGE_GUI_CONFIGURATION = "change_gui_config"
SERVICE_GET_ACTIVE_PLAYBOOK = "get_active_playbook"
SERVICE_GET_GROUP_ENTITIES = "get_group_entities"
SERVICE_INCREASE_DAILY_ENERGY = "increase_daily_energy"
SERVICE_RESET_ENERGY = "reset_energy"
SERVICE_STOP_PLAYBOOK = "stop_playbook"
SERVICE_SWITCH_SUB_PROFILE = "switch_sub_profile"
SERVICE_UPDATE_LIBRARY = "update_library"
SERVICE_RELOAD = "reload"

SIGNAL_POWER_SENSOR_STATE_CHANGE = "powercalc_power_sensor_state_change"

OFF_STATES = {STATE_OFF, STATE_STANDBY, STATE_UNAVAILABLE}
OFF_STATES_BY_DOMAIN: dict[str, set[str]] = {
    cover.DOMAIN: {STATE_CLOSED, STATE_OPEN},
    device_tracker.DOMAIN: {STATE_NOT_HOME},
}


class CalculationStrategy(StrEnum):
    """Possible virtual power calculation strategies."""

    COMPOSITE = "composite"
    LUT = "lut"
    LINEAR = "linear"
    MULTI_SWITCH = "multi_switch"
    FIXED = "fixed"
    PLAYBOOK = "playbook"
    WLED = "wled"


CALCULATION_STRATEGY_CONF_KEYS: list[str] = [strategy.value for strategy in CalculationStrategy]


class SensorType(StrEnum):
    """Possible modes for a number selector."""

    DAILY_ENERGY = "daily_energy"
    VIRTUAL_POWER = "virtual_power"
    GROUP = "group"
    REAL_POWER = "real_power"


class PowercalcDiscoveryType(StrEnum):
    DOMAIN_GROUP = "domain_group"
    STANDBY_GROUP = "standby_group"
    LIBRARY = "library"
    USER_YAML = "user_yaml"


class GroupType(StrEnum):
    """Possible group types."""

    CUSTOM = "custom"
    DOMAIN = "domain"
    STANDBY = "standby"
    SUBTRACT = "subtract"
    TRACKED_UNTRACKED = "tracked_untracked"
