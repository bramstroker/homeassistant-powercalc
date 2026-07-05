from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.const import CONF_ENABLED, CONF_ENTITY_ID, CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.issue_registry import IssueRegistry
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_device_registry

from custom_components.powercalc import (
    CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED,
    CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED,
    CONF_GROUP_UPDATE_INTERVAL_DEPRECATED,
    DOMAIN,
    DeviceType,
    async_fix_legacy_profile_config_entry,
    async_migrate_entry,
)
from custom_components.powercalc.config_flow import PowercalcConfigFlow
from custom_components.powercalc.const import (
    CONF_DISCOVERY,
    CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED,
    CONF_ENABLE_AUTODISCOVERY_DEPRECATED,
    CONF_ENERGY_UPDATE_INTERVAL,
    CONF_EXCLUDE_DEVICE_TYPES,
    CONF_EXCLUDE_SELF_USAGE,
    CONF_FIXED,
    CONF_GROUP_ENERGY_UPDATE_INTERVAL,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_SENSOR_TYPE,
    CONF_STATE,
    CONF_STATE_TRIGGER,
    CONF_STATES_POWER,
    CONF_STATES_TRIGGER,
    DUMMY_ENTITY_ID,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.power_profile.library import ModelInfo
from tests.common import migrate_legacy_entry, run_powercalc_setup


async def test_legacy_discovery_config_raises_issue(hass: HomeAssistant, issue_registry: IssueRegistry) -> None:
    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED: True,
        },
    )

    assert issue_registry.async_get_issue(DOMAIN, "legacy_discovery_config")


async def test_legacy_update_interval_config_issue_raised(hass: HomeAssistant, issue_registry: IssueRegistry) -> None:
    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_GROUP_UPDATE_INTERVAL_DEPRECATED: 80,
            CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED: timedelta(minutes=15),
        },
    )

    assert issue_registry.async_get_issue(DOMAIN, "legacy_update_interval_config")

    global_config = hass.data[DOMAIN]["config"]
    assert global_config[CONF_GROUP_ENERGY_UPDATE_INTERVAL] == 80
    assert global_config[CONF_ENERGY_UPDATE_INTERVAL] == 900
    assert CONF_GROUP_UPDATE_INTERVAL_DEPRECATED not in global_config
    assert CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED not in global_config


async def test_legacy_update_interval_config_issue_not_raised(
    hass: HomeAssistant,
    issue_registry: IssueRegistry,
) -> None:
    await run_powercalc_setup(hass)

    assert not issue_registry.async_get_issue(DOMAIN, "legacy_update_interval_config")


async def test_migrate_config_entry_playbooks(hass: HomeAssistant) -> None:
    """Test migration of a config entry to version 6"""
    mock_entry = await migrate_legacy_entry(
        hass,
        {
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
    assert mock_entry.data[CONF_PLAYBOOK][CONF_PLAYBOOKS] == [
        {"id": "evening_playbook", "path": "evening_playbook.yaml"},
        {"id": "morning_playbook", "path": "morning_playbook.yaml"},
    ]


async def test_migrate_config_entry_version_4(hass: HomeAssistant) -> None:
    """
    Test that a config entry is migrated from version 3 to version 4.
    """
    entry = await migrate_legacy_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "testentry",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_PLAYBOOK: {
                CONF_STATES_TRIGGER: {
                    "foo": "bar",
                },
            },
        },
        version=3,
    )
    assert entry.data == {
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_NAME: "testentry",
        CONF_ENTITY_ID: DUMMY_ENTITY_ID,
        CONF_PLAYBOOK: {
            CONF_STATE_TRIGGER: {
                "foo": "bar",
            },
        },
    }


async def test_migrate_config_entry_version_5(hass: HomeAssistant) -> None:
    """
    Test that a config entry is migrated from version 4 to version 5.
    """
    entry = await migrate_legacy_entry(
        hass,
        {
            CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED: True,
            CONF_DISCOVERY_EXCLUDE_DEVICE_TYPES_DEPRECATED: [DeviceType.COVER],
            CONF_ENABLE_AUTODISCOVERY_DEPRECATED: False,
        },
        version=4,
        entry_id=ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    )
    assert entry.data == {
        CONF_DISCOVERY: {
            CONF_ENABLED: False,
            CONF_EXCLUDE_DEVICE_TYPES: [DeviceType.COVER],
            CONF_EXCLUDE_SELF_USAGE: True,
        },
    }


async def test_migrate_config_entry_states_power(hass: HomeAssistant) -> None:
    """Test migration of states_power from dict to list format (version 6 to 7)."""
    mock_entry = await migrate_legacy_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {
                CONF_STATES_POWER: {
                    "playing": 20,
                    "paused": 5,
                    "idle": 2,
                },
            },
        },
        version=6,
    )
    assert mock_entry.data[CONF_FIXED][CONF_STATES_POWER] == [
        {CONF_STATE: "playing", CONF_POWER: 20},
        {CONF_STATE: "paused", CONF_POWER: 5},
        {CONF_STATE: "idle", CONF_POWER: 2},
    ]


async def test_migrate_config_entry_removes_invalid_power_sensor_category(hass: HomeAssistant) -> None:
    """Test migration removes the no longer valid config entity category from power sensors."""
    mock_entry = await migrate_legacy_entry(
        hass,
        {
            CONF_POWER_SENSOR_CATEGORY: EntityCategory.CONFIG,
        },
        version=7,
    )

    assert CONF_POWER_SENSOR_CATEGORY not in mock_entry.data


async def test_migrate_config_entry_keeps_diagnostic_power_sensor_category(hass: HomeAssistant) -> None:
    """Test migration keeps still valid power sensor categories."""
    mock_entry = await migrate_legacy_entry(
        hass,
        {
            CONF_POWER_SENSOR_CATEGORY: EntityCategory.DIAGNOSTIC,
        },
        version=7,
    )

    assert mock_entry.data[CONF_POWER_SENSOR_CATEGORY] == EntityCategory.DIAGNOSTIC


async def test_migrate_config_entry_removes_config_entry_from_device(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test migration removes the Powercalc config entry from devices."""
    device_registry = mock_device_registry(hass, {})
    device_owner_config_entry = MockConfigEntry(domain="test")
    device_owner_config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=device_owner_config_entry.entry_id,
        identifiers={("shelly", "PlugS")},
        manufacturer="shelly",
        model="PlugS",
    )
    entity_registry.async_get_or_create(
        "switch",
        "test",
        "source_switch",
        suggested_object_id="source_switch",
        device_id=device_entry.id,
    )

    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "switch.source_switch",
            CONF_FIXED: {CONF_POWER: 50},
        },
        version=8,
    )
    mock_entry.add_to_hass(hass)
    device_registry.async_update_device(device_entry.id, add_config_entry_id=mock_entry.entry_id)
    entity_entry = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "test_power",
        config_entry=mock_entry,
        device_id=device_entry.id,
    )

    device = device_registry.async_get(device_entry.id)
    assert device
    assert mock_entry.entry_id in device.config_entries
    assert entity_entry.device_id == device_entry.id

    await async_migrate_entry(hass, mock_entry)

    device = device_registry.async_get(device_entry.id)
    assert device
    assert mock_entry.entry_id not in device.config_entries
    entity_entry = entity_registry.async_get(entity_entry.entity_id)
    assert entity_entry
    assert entity_entry.device_id == device_entry.id
    assert mock_entry.version == PowercalcConfigFlow.VERSION


@pytest.mark.parametrize(
    ("input_model", "migrated_profile", "expected_model", "expect_update"),
    [
        ("33955", ModelInfo("eglo", "900053"), "900053", True),
        ("33955/default", ModelInfo("eglo", "900053"), "900053/default", True),
        ("Totari-Z 380", None, "Totari-Z 380", False),
        ("900053", ModelInfo("eglo", "900053"), "900053", False),
    ],
)
async def test_fix_legacy_library_model_reference(
    hass: HomeAssistant,
    input_model: str,
    migrated_profile: ModelInfo | None,
    expected_model: str,
    expect_update: bool,
) -> None:
    """Test always-on normalization of legacy library model ids."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "eglo",
            CONF_MODEL: input_model,
        },
        version=PowercalcConfigFlow.VERSION,
    )
    mock_entry.add_to_hass(hass)

    library = Mock()
    library.find_model_migration = AsyncMock(return_value=migrated_profile)

    with (
        patch("custom_components.powercalc.migrate.ProfileLibrary.factory", AsyncMock(return_value=library)),
        patch.object(
            hass.config_entries,
            "async_update_entry",
            wraps=hass.config_entries.async_update_entry,
        ) as mock_update_entry,
    ):
        await async_fix_legacy_profile_config_entry(hass, mock_entry)

    if expect_update:
        mock_update_entry.assert_called_once()
    else:
        mock_update_entry.assert_not_called()

    assert mock_entry.version == PowercalcConfigFlow.VERSION
    assert mock_entry.data[CONF_MODEL] == expected_model
