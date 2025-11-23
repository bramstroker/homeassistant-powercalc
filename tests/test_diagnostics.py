from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import CONF_SENSOR_TYPE, SensorType
from custom_components.powercalc.const import CONF_FIXED, CONF_GROUP_MEMBER_SENSORS, CONF_MODE, CONF_POWER, CalculationStrategy
from custom_components.powercalc.diagnostics import async_get_config_entry_diagnostics
from tests.common import get_test_config_dir, setup_config_entry


async def test_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_config_entry.add_to_hass(hass)
    diagnostics_data = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert diagnostics_data == {
        "entry": mock_config_entry.as_dict(),
        "config_entry_count_per_type": {
            SensorType.VIRTUAL_POWER: 1,
        },
        "yaml_config": {},
    }


async def test_group_entities_are_included_in_diagnostics(hass: HomeAssistant) -> None:
    member_entry = await setup_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_NAME: "Test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )
    group_entry = await setup_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_MEMBER_SENSORS: [member_entry.entry_id],
        },
    )

    diagnostics_data = await async_get_config_entry_diagnostics(hass, group_entry)
    assert diagnostics_data == {
        "entry": group_entry.as_dict(),
        "energy_entities": {"sensor.test_energy"},
        "power_entities": {"sensor.test_power"},
        "config_entry_count_per_type": {
            SensorType.VIRTUAL_POWER: 1,
            SensorType.GROUP: 1,
        },
        "yaml_config": {},
    }


async def test_yaml_config_included(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    hass.config.config_dir = get_test_config_dir()
    mock_config_entry.add_to_hass(hass)

    diagnostics_data = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert diagnostics_data == {
        "entry": mock_config_entry.as_dict(),
        "yaml_config": {
            "discovery": {
                "enabled": True,
            },
        },
        "config_entry_count_per_type": {
            SensorType.VIRTUAL_POWER: 1,
        },
    }
