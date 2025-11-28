from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENABLED, CONF_ID, CONF_PATH
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
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_POWER,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STATE_TRIGGER,
    CONF_STATES_TRIGGER,
    DOMAIN,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
)


async def async_migrate_config_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    version = config_entry.version
    data = {**config_entry.data}

    if version <= 1:
        conf_fixed = data.get(CONF_FIXED, {})
        if CONF_POWER in conf_fixed and CONF_POWER_TEMPLATE in conf_fixed:
            conf_fixed.pop(CONF_POWER, None)

    if version <= 2 and data.get(CONF_SENSOR_TYPE) and CONF_CREATE_ENERGY_SENSOR not in data:
        data[CONF_CREATE_ENERGY_SENSOR] = True

    if version <= 3:
        conf_playbook = data.get(CONF_PLAYBOOK, {})
        if CONF_STATES_TRIGGER in conf_playbook:
            data[CONF_PLAYBOOK][CONF_STATE_TRIGGER] = conf_playbook.pop(CONF_STATES_TRIGGER)

    if version <= 4 and config_entry.entry_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID:
        discovery_config = {
            CONF_ENABLED: data.get(CONF_ENABLE_AUTODISCOVERY_DEPRECATED, True),
            CONF_EXCLUDE_DEVICE_TYPES: data.get(CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED, []),
            CONF_EXCLUDE_SELF_USAGE: data.get(CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED, False),
        }
        data[CONF_DISCOVERY] = discovery_config
        for key in [
            CONF_ENABLE_AUTODISCOVERY_DEPRECATED,
            CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED,
            CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED,
        ]:
            data.pop(key, None)

    if version <= 5:
        conf_playbook = data.get(CONF_PLAYBOOK, {})
        if CONF_PLAYBOOKS in conf_playbook:
            data[CONF_PLAYBOOK][CONF_PLAYBOOKS] = [{CONF_ID: key, CONF_PATH: val} for key, val in conf_playbook.pop(CONF_PLAYBOOKS).items()]

    hass.config_entries.async_update_entry(config_entry, data=data, version=6)


async def handle_legacy_discovery_config(hass: HomeAssistant, global_config: dict, yaml_config: dict) -> None:
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


async def handle_legacy_update_interval_config(hass: HomeAssistant, global_config: dict, yaml_config: dict) -> None:
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
