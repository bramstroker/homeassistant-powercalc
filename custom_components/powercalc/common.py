from dataclasses import dataclass
import math
import re
from typing import TYPE_CHECKING, cast

from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant, split_entity_id
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import (
    CONF_CREATE_COST_SENSOR,
    CONF_CREATE_COST_SENSORS,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_GROUP,
    CONF_DAILY_FIXED_ENERGY,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_SENSOR,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_MULTI_SWITCH,
    CONF_POWER_SENSOR_ID,
    CONF_SENSOR_TYPE,
    DUMMY_ENTITY_ID,
    SensorType,
)
from .errors import SensorConfigurationError

_HAS_CHILD_DEVICES = hasattr(dr, "ChildDeviceEntry")

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import AnyDeviceEntry as AnyDeviceEntry
else:
    # AnyDeviceEntry was introduced together with child devices in HA 2026.9.
    # Keep imports working on older supported versions, where every entry is a DeviceEntry.
    AnyDeviceEntry = dr.DeviceEntry


@dataclass(frozen=True)
class SourceEntity:
    """The appliance a powercalc sensor measures, resolved from the entity and device registry."""

    object_id: str
    entity_id: str
    domain: str
    unique_id: str | None = None
    name: str | None = None
    entity_entry: er.RegistryEntry | None = None
    device_entry: AnyDeviceEntry | None = None
    config_entry_id: str | None = None

    @property
    def is_dummy(self) -> bool:
        """Whether this source has no real entity behind it, such as a daily fixed energy or group sensor."""
        return self.entity_id == DUMMY_ENTITY_ID

    @property
    def device_id(self) -> str | None:
        """The ID of the device this source belongs to, when it is bound to one."""
        return self.device_entry.id if self.device_entry else None

    @property
    def log_identifier(self) -> str:
        """Build a label identifying this source, used as prefix for log messages about it."""
        if self.config_entry_id:
            return _label("config_entry", self.config_entry_id, self.name)
        if self.entity_id and not self.is_dummy:
            return self.entity_id
        if self.device_entry:
            return _label("device", self.device_entry.id, self.device_entry.name_by_user or self.device_entry.name)
        return self.object_id  # pragma: no cover


def _label(prefix: str, identifier: str, name: str | None) -> str:
    """Build `prefix id (name)`, omitting the name when the registry does not have one."""
    return f"{prefix} {identifier} ({name})" if name else f"{prefix} {identifier}"


EXCLUDE_FROM_PARENT_CONFIG = (
    CONF_NAME,
    CONF_ENTITY_ID,
    CONF_UNIQUE_ID,
    CONF_POWER_SENSOR_ID,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
)
ENTITY_ID_OPTIONAL_KEYS = (CONF_DAILY_FIXED_ENERGY, CONF_POWER_SENSOR_ID, CONF_MULTI_SWITCH)

# Groups of keys where a deeper config level replaces the whole group, instead of merging
# key by key. A sensor defining `energy_price` must fully override a global
# `energy_price_sensor`, otherwise the merged config would contain both price sources.
MUTUALLY_EXCLUSIVE_KEY_GROUPS = ((CONF_ENERGY_PRICE, CONF_ENERGY_PRICE_SENSOR),)


def is_number(value: str) -> bool:
    """Return whether the value can be converted to a finite float."""
    try:
        fvalue = float(value)
    except TypeError, ValueError:
        return False
    return math.isfinite(fvalue)


def get_main_device_entry(device_registry: dr.DeviceRegistry, device_id: str) -> dr.DeviceEntry | None:
    """Return a main device entry, excluding child devices on versions which support them."""
    if _HAS_CHILD_DEVICES:
        return device_registry.async_get(device_id, include_child_devices=False)
    return cast(dr.DeviceEntry | None, device_registry.async_get(device_id))  # pragma: no cover


def create_source_entity(entity_id: str, hass: HomeAssistant) -> SourceEntity:
    """Create object containing all information about the source entity."""

    source_entity_domain, source_object_id = split_entity_id(entity_id)
    if entity_id == DUMMY_ENTITY_ID:
        return SourceEntity(
            object_id=source_object_id,
            entity_id=DUMMY_ENTITY_ID,
            domain=source_entity_domain,
        )

    entity_registry = er.async_get(hass)
    entity_entry = entity_registry.async_get(entity_id)

    device_registry = dr.async_get(hass)
    device_entry = (
        device_registry.async_get(entity_entry.device_id) if entity_entry and entity_entry.device_id else None
    )

    unique_id = None
    if entity_entry:
        source_entity_domain = entity_entry.domain
        unique_id = entity_entry.unique_id

    return SourceEntity(
        source_object_id,
        entity_id,
        source_entity_domain,
        unique_id,
        get_wrapped_entity_name(
            hass,
            entity_id,
            source_object_id,
            entity_entry,
            device_entry,
        ),
        entity_entry,
        device_entry,
    )


def get_wrapped_entity_name(
    hass: HomeAssistant,
    entity_id: str,
    object_id: str,
    entity_entry: er.RegistryEntry | None,
    device_entry: AnyDeviceEntry | None,
) -> str:
    """Construct entity name based on the wrapped entity"""
    if entity_entry is None:
        return _get_state_name(hass, entity_id) or object_id

    if entity_entry.name:
        return entity_entry.name

    device_entity_name = _get_device_entity_name(entity_entry, device_entry)
    if device_entity_name:
        return device_entity_name

    return entity_entry.original_name or object_id


def _get_device_entity_name(
    entity_entry: er.RegistryEntry,
    device_entry: AnyDeviceEntry | None,
) -> str | None:
    if not entity_entry.has_entity_name or device_entry is None:
        return None

    device_name = device_entry.name_by_user or device_entry.name
    if not device_name:
        return None

    if entity_entry.original_name:
        return f"{device_name} {entity_entry.original_name}"

    return device_name


def _get_state_name(hass: HomeAssistant, entity_id: str) -> str | None:
    entity_state = hass.states.get(entity_id)
    return str(entity_state.name) if entity_state else None


def get_merged_sensor_configuration(*configs: ConfigType, validate: bool = True) -> ConfigType:
    """Merges configuration from multiple levels (global, group, sensor) into a single ConfigType."""
    merged_config = _merge_config_levels(configs)
    _apply_sensor_creation_defaults(merged_config)
    _apply_dummy_entity_id_default(merged_config)
    _validate_entity_id_config(merged_config, validate)

    return merged_config


def _merge_config_levels(configs: tuple[ConfigType, ...]) -> ConfigType:
    """Merge config levels while keeping deepest-level-only fields local."""
    num_configs = len(configs)

    merged_config: ConfigType = {}
    for i, config in enumerate(configs, 1):
        config_copy = config.copy()
        if i < num_configs:
            for key in EXCLUDE_FROM_PARENT_CONFIG:
                config_copy.pop(key, None)

        _drop_overridden_alternatives(merged_config, config_copy)
        merged_config.update(config_copy)
    return merged_config


def _drop_overridden_alternatives(merged_config: ConfigType, config: ConfigType) -> None:
    """Drop the alternatives of a mutually exclusive key group set by a shallower config level."""
    for group in MUTUALLY_EXCLUSIVE_KEY_GROUPS:
        if not any(key in config for key in group):
            continue
        for key in group:
            if key not in config:
                merged_config.pop(key, None)


def _apply_sensor_creation_defaults(config: ConfigType) -> None:
    config.setdefault(CONF_CREATE_ENERGY_SENSOR, config.get(CONF_CREATE_ENERGY_SENSORS))
    config.setdefault(CONF_CREATE_COST_SENSOR, config.get(CONF_CREATE_COST_SENSORS))


def _apply_dummy_entity_id_default(config: ConfigType) -> None:
    if CONF_ENTITY_ID in config:
        return
    # A standalone cost sensor has no source appliance entity, use the dummy placeholder.
    if not _is_entity_id_required(config) or config.get(CONF_SENSOR_TYPE) == SensorType.COST:
        config[CONF_ENTITY_ID] = DUMMY_ENTITY_ID


def _is_entity_id_required(config: ConfigType) -> bool:
    return not any(key in config for key in ENTITY_ID_OPTIONAL_KEYS)


def _validate_entity_id_config(config: ConfigType, validate: bool) -> None:
    if _is_missing_required_entity_id(config, validate):
        raise SensorConfigurationError(
            "You must supply an entity_id in the configuration, see the README",
        )


def _is_missing_required_entity_id(config: ConfigType, validate: bool) -> bool:
    sensor_type = config.get(CONF_SENSOR_TYPE)
    return (
        validate
        and CONF_CREATE_GROUP not in config
        and CONF_ENTITY_ID not in config
        and sensor_type != SensorType.GROUP
    )


def validate_name_pattern(value: str) -> str:
    """Validate that the naming pattern contains {}."""
    regex = re.compile(r"{}")
    if not regex.search(value):
        raise vol.Invalid("Naming pattern must contain {}")
    return value


def validate_is_number(value: str) -> str:
    """Validate value is a number."""
    if is_number(value):
        return value
    raise vol.Invalid("Value is not a number")
