from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENABLED, CONF_ID, CONF_PATH, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.issue_registry import async_create_issue

from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_DISCOVERY,
    CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED,
    CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED,
    CONF_ENABLE_AUTODISCOVERY_DEPRECATED,
    CONF_ENERGY_UPDATE_INTERVAL,
    CONF_EXCLUDE_DEVICE_TYPES,
    CONF_EXCLUDE_SELF_USAGE,
    CONF_FIXED,
    CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED,
    CONF_GROUP_ENERGY_UPDATE_INTERVAL,
    CONF_GROUP_UPDATE_INTERVAL_DEPRECATED,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STATE,
    CONF_STATE_TRIGGER,
    CONF_STATES_POWER,
    CONF_STATES_TRIGGER,
    DOMAIN,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
)
from custom_components.powercalc.power_profile.library import ModelInfo, ProfileLibrary


async def async_migrate_config_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    version = config_entry.version
    data = {**config_entry.data}

    if version <= 1:
        _migrate_power_template(data)

    if version <= 2 and data.get(CONF_SENSOR_TYPE) and CONF_CREATE_ENERGY_SENSOR not in data:
        data[CONF_CREATE_ENERGY_SENSOR] = True

    if version <= 3:
        _migrate_playbook_trigger(data)

    if version <= 4 and config_entry.entry_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID:
        _migrate_global_discovery_config(data)

    if version <= 5:
        _migrate_playbooks(data)

    if version <= 6:
        _migrate_states_power(data)

    if version <= 7:
        _migrate_invalid_power_sensor_category(data)

    hass.config_entries.async_update_entry(config_entry, data=data, version=8)


def _migrate_power_template(data: dict) -> None:
    conf_fixed = data.get(CONF_FIXED, {})
    if CONF_POWER in conf_fixed and CONF_POWER_TEMPLATE in conf_fixed:
        conf_fixed.pop(CONF_POWER, None)


def _migrate_playbook_trigger(data: dict) -> None:
    conf_playbook = data.get(CONF_PLAYBOOK, {})
    if CONF_STATES_TRIGGER in conf_playbook:
        data[CONF_PLAYBOOK][CONF_STATE_TRIGGER] = conf_playbook.pop(CONF_STATES_TRIGGER)


def _migrate_global_discovery_config(data: dict) -> None:
    data[CONF_DISCOVERY] = {
        CONF_ENABLED: data.get(CONF_ENABLE_AUTODISCOVERY_DEPRECATED, True),
        CONF_EXCLUDE_DEVICE_TYPES: data.get(CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED, []),
        CONF_EXCLUDE_SELF_USAGE: data.get(CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED, False),
    }
    for key in [
        CONF_ENABLE_AUTODISCOVERY_DEPRECATED,
        CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED,
        CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED,
    ]:
        data.pop(key, None)


def _migrate_playbooks(data: dict) -> None:
    conf_playbook = data.get(CONF_PLAYBOOK, {})
    if CONF_PLAYBOOKS in conf_playbook:
        data[CONF_PLAYBOOK][CONF_PLAYBOOKS] = [
            {CONF_ID: key, CONF_PATH: val} for key, val in conf_playbook.pop(CONF_PLAYBOOKS).items()
        ]


def _migrate_states_power(data: dict) -> None:
    conf_fixed = data.get(CONF_FIXED, {})
    if CONF_STATES_POWER in conf_fixed and isinstance(conf_fixed[CONF_STATES_POWER], dict):
        data[CONF_FIXED][CONF_STATES_POWER] = [
            {CONF_STATE: key, CONF_POWER: val} for key, val in conf_fixed[CONF_STATES_POWER].items()
        ]


def _migrate_invalid_power_sensor_category(data: dict) -> None:
    if data.get(CONF_POWER_SENSOR_CATEGORY) == EntityCategory.CONFIG:
        data.pop(CONF_POWER_SENSOR_CATEGORY)


async def async_fix_legacy_profile_config_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Always normalize legacy profile references on setup, based on library metadata."""
    manufacturer = config_entry.data.get(CONF_MANUFACTURER)
    model = config_entry.data.get(CONF_MODEL)
    if not manufacturer or not model:
        return

    model_id = str(model)
    sub_profile = ""
    if "/" in model_id:
        model_id, sub_profile = model_id.split("/", 1)

    library = await ProfileLibrary.factory(hass)
    migrated_profile = await library.find_model_migration(ModelInfo(str(manufacturer), model_id))
    if migrated_profile is None:
        return

    resolved_manufacturer = migrated_profile.manufacturer
    migrated_model = migrated_profile.model
    if migrated_model == model_id and str(manufacturer).lower() == resolved_manufacturer.lower():
        return

    updated_model = f"{migrated_model}/{sub_profile}" if sub_profile else migrated_model
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            CONF_MANUFACTURER: resolved_manufacturer,
            CONF_MODEL: updated_model,
        },
    )


def handle_legacy_discovery_config(hass: HomeAssistant, global_config: dict, yaml_config: dict) -> None:
    """Handle legacy discovery config. Might be removed in future Powercalc version"""
    discovery_options = global_config.setdefault(CONF_DISCOVERY, {})
    deprecated_map = {
        CONF_EXCLUDE_DEVICE_TYPES: CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED,
        CONF_EXCLUDE_SELF_USAGE: CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED,
        CONF_ENABLED: CONF_ENABLE_AUTODISCOVERY_DEPRECATED,
    }

    legacy_discovery_config = False
    for new_key, old_key in deprecated_map.items():
        if old_key not in yaml_config:
            continue

        discovery_options[new_key] = yaml_config[old_key]  # pragma: nocover

        global_config.pop(old_key, None)
        legacy_discovery_config = True

    if not legacy_discovery_config:
        return

    async_create_issue(
        hass=hass,
        domain=DOMAIN,
        issue_id="legacy_discovery_config",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="legacy_config",
        translation_placeholders={
            "type": "discovery",
        },
        learn_more_url="https://docs.powercalc.nl/configuration/migration/discovery-config",
        breaks_in_ha_version="2026.06",
    )


def handle_legacy_update_interval_config(hass: HomeAssistant, global_config: dict, yaml_config: dict) -> None:
    """Handle legacy group update interval config. Might be removed in future Powercalc version"""

    has_legacy_config = False
    if CONF_GROUP_UPDATE_INTERVAL_DEPRECATED in yaml_config:
        global_config[CONF_GROUP_ENERGY_UPDATE_INTERVAL] = yaml_config[CONF_GROUP_UPDATE_INTERVAL_DEPRECATED]
        global_config.pop(CONF_GROUP_UPDATE_INTERVAL_DEPRECATED, None)
        has_legacy_config = True

    if CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED in yaml_config:
        legacy_config = yaml_config[CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED]
        if isinstance(legacy_config, timedelta):
            legacy_config = legacy_config.seconds
        global_config[CONF_ENERGY_UPDATE_INTERVAL] = legacy_config
        global_config.pop(CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED, None)
        has_legacy_config = True

    if not has_legacy_config:
        return

    async_create_issue(
        hass=hass,
        domain=DOMAIN,
        issue_id="legacy_update_interval_config",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="legacy_config",
        translation_placeholders={
            "type": "group_update_interval",
        },
        learn_more_url="https://docs.powercalc.nl/configuration/migration/update-interval-config",
        breaks_in_ha_version="2026.06",
    )
