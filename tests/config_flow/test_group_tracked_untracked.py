import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import (
    CONF_NAME,
    CONF_SENSOR_TYPE,
)
from homeassistant.core import HomeAssistant

from custom_components.powercalc import SensorType
from custom_components.powercalc.config_flow import UNIQUE_ID_TRACKED_UNTRACKED, Step
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_GROUP_TRACKED_AUTO,
    CONF_GROUP_TRACKED_POWER_ENTITIES,
    CONF_GROUP_TYPE,
    CONF_MAIN_POWER_SENSOR,
    DOMAIN,
    GroupType,
)
from tests.common import mock_sensors_in_registry, run_powercalc_setup
from tests.config_flow.common import (
    create_mock_entry,
    initialize_options_flow,
    select_menu_item,
)


async def test_config_flow(hass: HomeAssistant) -> None:
    """Test the tracked/untracked group flow."""

    await run_powercalc_setup(hass)
    mock_sensors_in_registry(hass, ["sensor.1_power", "sensor.2_power"])

    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_TRACKED_UNTRACKED)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    user_input = {
        CONF_MAIN_POWER_SENSOR: "sensor.mains_power",
        CONF_GROUP_TRACKED_AUTO: True,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
        CONF_NAME: "Tracked / Untracked",
        CONF_MAIN_POWER_SENSOR: "sensor.mains_power",
        CONF_GROUP_TRACKED_AUTO: True,
    }

    hass.states.async_set("sensor.mains_power", "100")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.1_power", "10")
    hass.states.async_set("sensor.2_power", "20")
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    tracked_power_state = hass.states.get("sensor.tracked_power")
    assert tracked_power_state
    assert tracked_power_state.state == "30.00"

    untracked_power_state = hass.states.get("sensor.untracked_power")
    assert untracked_power_state
    assert untracked_power_state.state == "70.00"


async def test_config_flow_manual(hass: HomeAssistant) -> None:
    """Test the tracked/untracked group flow."""
    await run_powercalc_setup(hass)
    mock_sensors_in_registry(hass, ["sensor.1_power", "sensor.2_power"])

    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_TRACKED_UNTRACKED)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MAIN_POWER_SENSOR: "sensor.mains_power",
            CONF_GROUP_TRACKED_AUTO: False,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GROUP_TRACKED_UNTRACKED_MANUAL

    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_GROUP_TRACKED_POWER_ENTITIES)].description == {"suggested_value": ["sensor.1_power", "sensor.2_power"]}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_GROUP_TRACKED_POWER_ENTITIES: ["sensor.1_power", "sensor.2_power"],
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    assert result["data"] == {
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
        CONF_NAME: "Tracked / Untracked",
        CONF_MAIN_POWER_SENSOR: "sensor.mains_power",
        CONF_GROUP_TRACKED_AUTO: False,
        CONF_GROUP_TRACKED_POWER_ENTITIES: ["sensor.1_power", "sensor.2_power"],
    }

    hass.states.async_set("sensor.mains_power", "100")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.1_power", "10")
    hass.states.async_set("sensor.2_power", "20")
    await hass.async_block_till_done()
    await hass.async_block_till_done()

    tracked_power_state = hass.states.get("sensor.tracked_power")
    assert tracked_power_state
    assert tracked_power_state.state == "30.00"

    untracked_power_state = hass.states.get("sensor.untracked_power")
    assert untracked_power_state
    assert untracked_power_state.state == "70.00"


async def test_only_single_instance(hass: HomeAssistant) -> None:
    """Only one instance of tracked/untracked allowed. Check if it is removed from the menu"""
    entry = create_mock_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_NAME: "Tracked / Untracked",
            CONF_MAIN_POWER_SENSOR: "sensor.mains_power",
            CONF_GROUP_TRACKED_AUTO: True,
        },
        unique_id=UNIQUE_ID_TRACKED_UNTRACKED,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": Step.MENU_GROUP},
    )
    menu_items = result["menu_options"]
    assert Step.GROUP_TRACKED_UNTRACKED not in menu_items


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_NAME: "Tracked / Untracked",
            CONF_MAIN_POWER_SENSOR: "sensor.mains_power",
            CONF_GROUP_TRACKED_AUTO: True,
        },
    )

    result = await initialize_options_flow(hass, entry, Step.GROUP_TRACKED_UNTRACKED)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_GROUP_TRACKED_AUTO: False},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert not entry.data[CONF_GROUP_TRACKED_AUTO]

    result = await initialize_options_flow(hass, entry, Step.GROUP_TRACKED_UNTRACKED_MANUAL)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_GROUP_TRACKED_POWER_ENTITIES: ["sensor.1_power", "sensor.2_power"]},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_GROUP_TRACKED_POWER_ENTITIES] == ["sensor.1_power", "sensor.2_power"]
