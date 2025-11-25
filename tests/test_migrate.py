from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import (
    CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED,
    CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED,
    CONF_GROUP_UPDATE_INTERVAL_DEPRECATED,
    DOMAIN,
    async_migrate_entry,
)
from custom_components.powercalc.config_flow import PowercalcConfigFlow
from custom_components.powercalc.const import (
    CONF_ENERGY_UPDATE_INTERVAL,
    CONF_GROUP_ENERGY_UPDATE_INTERVAL,
    CONF_MODE,
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_SENSOR_TYPE,
    CalculationStrategy,
    SensorType,
)
from tests.common import run_powercalc_setup


async def test_legacy_discovery_config_raises_issue(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED: True,
        },
    )

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, "legacy_discovery_config")
    assert issue


async def test_legacy_update_interval_config_issue_raised(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_GROUP_UPDATE_INTERVAL_DEPRECATED: 80,
            CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED: timedelta(minutes=15),
        },
    )

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, "legacy_update_interval_config")
    assert issue

    global_config = hass.data[DOMAIN]["config"]
    assert global_config[CONF_GROUP_ENERGY_UPDATE_INTERVAL] == 80
    assert global_config[CONF_ENERGY_UPDATE_INTERVAL] == 900
    assert CONF_GROUP_UPDATE_INTERVAL_DEPRECATED not in global_config
    assert CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED not in global_config


async def test_legacy_update_interval_config_issue_not_raised(hass: HomeAssistant) -> None:
    await run_powercalc_setup(hass)

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, "legacy_update_interval_config")
    assert not issue


async def test_migrate_config_entry_playbooks(hass: HomeAssistant) -> None:
    """Test migration of a config entry to version 6"""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.PLAYBOOK,
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "evening_playbook": "evening_playbook.yaml",
                    "morning_playbook": "morning_playbook.yaml",
                },
            },
        },
        version=5,
    )
    mock_entry.add_to_hass(hass)
    await async_migrate_entry(hass, mock_entry)
    hass.config_entries.async_get_entry(mock_entry.entry_id)
    assert mock_entry.version == PowercalcConfigFlow.VERSION
    assert mock_entry.data[CONF_PLAYBOOK][CONF_PLAYBOOKS] == [
        {"id": "evening_playbook", "path": "evening_playbook.yaml"},
        {"id": "morning_playbook", "path": "morning_playbook.yaml"},
    ]
