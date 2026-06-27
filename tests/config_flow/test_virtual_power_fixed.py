from unittest.mock import MagicMock, patch

from homeassistant import data_entry_flow
from homeassistant.const import ATTR_FRIENDLY_NAME, ATTR_ICON, CONF_ENTITY_ID, CONF_NAME, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
from voluptuous_serialize import convert

from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_FIXED,
    CONF_FIXED_VALUE,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_POWER,
    CONF_STATE,
    CONF_STATES_POWER,
    ENERGY_INTEGRATION_METHOD_RIGHT,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.flow_helper.profile_preview import ws_start_preview
from tests.common import create_mock_config_entry, run_powercalc_setup
from tests.config_flow.common import (
    assert_default_virtual_power_entry_data,
    fixed_value_choice,
    goto_virtual_power_strategy_step,
    handle_options_flow_update,
    initialize_options_flow,
    process_config_flow,
    select_menu_item,
    set_virtual_power_configuration,
)


async def test_create_fixed_sensor_entry(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    assert result["preview"] == "powercalc"

    result = await set_virtual_power_configuration(hass, result, fixed_value_choice(CONF_POWER, 20))

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {CONF_FIXED: {CONF_POWER: 20}},
    )

    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_fixed_strategy_preview_websocket(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    hass.states.async_set("light.test", STATE_ON)

    connection = MagicMock()
    connection.subscriptions = {}
    ws_start_preview(
        hass,
        connection,
        {
            "id": 1,
            "type": "powercalc/start_preview",
            "flow_id": result["flow_id"],
            "flow_type": "config_flow",
            "user_input": fixed_value_choice(CONF_POWER, 20),
        },
    )
    await hass.async_block_till_done()

    connection.send_result.assert_called_once_with(1)

    event = connection.send_message.call_args.args[0]
    assert event["type"] == "event"
    assert event["event"]["attributes"][ATTR_FRIENDLY_NAME] == "Preview power"
    assert event["event"]["attributes"][ATTR_ICON] == "mdi:flash"
    assert event["event"]["state"] == "20 W"


async def test_create_fixed_sensor_entry_with_template(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)

    template = "{{states(input_number.my_number)}} | float"
    result = await set_virtual_power_configuration(
        hass,
        result,
        fixed_value_choice(CONF_POWER_TEMPLATE, template),
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {CONF_FIXED: {CONF_POWER_TEMPLATE: template}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_create_fixed_sensor_entry_with_states_power(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    result = await set_virtual_power_configuration(
        hass,
        result,
        fixed_value_choice(CONF_STATES_POWER, [{"state": "playing", "power": 1.8}]),
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {CONF_FIXED: {CONF_STATES_POWER: [{"state": "playing", "power": 1.8}]}},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_fixed_options_flow(hass: HomeAssistant) -> None:
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_IGNORE_UNAVAILABLE_STATE: False,
            CONF_FIXED: {CONF_POWER: 40},
        },
    )

    result = await initialize_options_flow(hass, entry, Step.BASIC_OPTIONS)

    schema_keys = list(result["data_schema"].schema.keys())
    assert schema_keys == [CONF_ENTITY_ID, CONF_STANDBY_POWER, CONF_CREATE_ENERGY_SENSOR, CONF_CREATE_UTILITY_METERS]

    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_ENTITY_ID: "light.test", CONF_CREATE_UTILITY_METERS: True},
    )

    await handle_options_flow_update(hass, entry, Step.FIXED, fixed_value_choice(CONF_POWER, 50))

    result = await handle_options_flow_update(hass, entry, Step.ADVANCED_OPTIONS, {CONF_IGNORE_UNAVAILABLE_STATE: True})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_FIXED][CONF_POWER] == 50
    assert entry.data[CONF_CREATE_UTILITY_METERS]
    assert entry.data[CONF_IGNORE_UNAVAILABLE_STATE]


async def test_fixed_options_flow_ignores_empty_states_power_when_power_is_set(hass: HomeAssistant) -> None:
    """Regression for issue #4239: stale empty states_power should not drive the fixed choice."""
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "switch.luz_exterior_foco_switch",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
            CONF_FIXED: {
                CONF_POWER: 47.0,
                CONF_STATES_POWER: [],
            },
        },
    )

    result = await initialize_options_flow(hass, entry, Step.FIXED)

    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_FIXED_VALUE)].default() == 47.0
    assert schema_keys[schema_keys.index(CONF_FIXED_VALUE)].description == {"suggested_value": 47.0}
    fixed_schema = convert(result["data_schema"], custom_serializer=cv.custom_serializer)[0]
    assert next(iter(fixed_schema["selector"]["choose"]["choices"])) == CONF_POWER
    assert fixed_schema["default"] == 47.0

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=fixed_value_choice(CONF_POWER, 50),
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_FIXED] == {CONF_POWER: 50}


async def test_fixed_states_power_options_flow(hass: HomeAssistant) -> None:
    """
    Test that we can configure the states power option.
    Also make sure conversion from dict to list is done correctly, and the order is preserved.
    """
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "sensor.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_IGNORE_UNAVAILABLE_STATE: False,
            CONF_FIXED: {CONF_STATES_POWER: [{"state": "2", "power": 50}, {"state": "4", "power": 20}]},
        },
    )

    result = await initialize_options_flow(hass, entry, Step.FIXED)

    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_FIXED_VALUE)].default() == [
        {"state": "2", "power": 50},
        {"state": "4", "power": 20},
    ]
    fixed_schema = convert(result["data_schema"], custom_serializer=cv.custom_serializer)[0]
    assert next(iter(fixed_schema["selector"]["choose"]["choices"])) == CONF_STATES_POWER
    states_power_selector = fixed_schema["selector"]["choose"]["choices"][CONF_STATES_POWER]["selector"]["object"]
    assert states_power_selector["label_field"] == CONF_STATE
    assert states_power_selector["description_field"] == CONF_POWER
    assert fixed_schema["default"] == [{"state": "2", "power": 50}, {"state": "4", "power": 20}]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=fixed_value_choice(
            CONF_STATES_POWER,
            [{"state": "4", "power": 20}, {"state": "2", "power": 50}, {"state": "6", "power": 200}],
        ),
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_FIXED][CONF_STATES_POWER] == [
        {"state": "4", "power": 20},
        {"state": "2", "power": 50},
        {"state": "6", "power": 200},
    ]


async def test_fixed_states_power_options_flow_reconstructs_existing_config(hass: HomeAssistant) -> None:
    states_power = [
        {"power": 3000, "state": "hvac_action|cooling"},
        {"power": 3200, "state": "hvac_action|heating"},
        {"power": 150, "state": "fan_mode|on"},
        {"power": 0, "state": "hvac_action|idle"},
        {"power": 0, "state": "hvac_action|off"},
    ]
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_IGNORE_UNAVAILABLE_STATE: False,
            CONF_FIXED: {CONF_STATES_POWER: states_power},
        },
    )

    result = await initialize_options_flow(hass, entry, Step.FIXED)
    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_FIXED_VALUE)].default() == states_power
    assert schema_keys[schema_keys.index(CONF_FIXED_VALUE)].description == {"suggested_value": states_power}
    fixed_schema = convert(result["data_schema"], custom_serializer=cv.custom_serializer)[0]
    assert next(iter(fixed_schema["selector"]["choose"]["choices"])) == CONF_STATES_POWER
    assert fixed_schema["default"] == states_power
    assert fixed_schema["description"] == {"suggested_value": states_power}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=fixed_value_choice(CONF_STATES_POWER, states_power),
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_FIXED][CONF_STATES_POWER] == states_power


async def test_fixed_options_hidden_from_menu_for_self_usage_profiles(hass: HomeAssistant) -> None:
    """
    Fixed options should be hidden from the menu for self usage profiles
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2935
    """
    entry = await create_mock_config_entry(
        hass,
        {
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "power_meter",
        },
    )

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == Step.INIT
    menu_options = result["menu_options"]
    assert Step.FIXED not in menu_options


async def test_strategy_raises_unknown_error(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.powercalc.strategy.fixed.FixedStrategy.validate_config",
        side_effect=StrategyConfigurationError("test"),
    ):
        result = await goto_virtual_power_strategy_step(
            hass,
            CalculationStrategy.FIXED,
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            fixed_value_choice(CONF_POWER, 20),
        )

        assert result["errors"]
        assert result["errors"]["base"] == "unknown"
        assert result["type"] == data_entry_flow.FlowResultType.FORM


async def test_advanced_power_configuration_can_be_set(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.FIXED)
    advanced_options = {
        CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('vacuum.my_robot_cleaner', 'docked') }}",
    }

    result = await set_virtual_power_configuration(
        hass,
        result,
        fixed_value_choice(CONF_POWER, 20),
        advanced_options,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    assert_default_virtual_power_entry_data(
        CalculationStrategy.FIXED,
        result["data"],
        {
            CONF_FIXED: {CONF_POWER: 20},
            CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('vacuum.my_robot_cleaner', 'docked') }}",
        },
    )


async def test_entity_selection_mandatory(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.VIRTUAL_POWER)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MODE: CalculationStrategy.FIXED,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"entity_id": "entity_mandatory"}


async def test_global_configuration_is_applied_to_field_default(
    hass: HomeAssistant,
) -> None:
    """Field should be set to match powercalc global configuration by default"""
    global_config = {
        CONF_CREATE_UTILITY_METERS: True,
        CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_RIGHT,
        CONF_IGNORE_UNAVAILABLE_STATE: True,
    }
    await run_powercalc_setup(hass, {}, global_config)

    result = await select_menu_item(hass, Step.VIRTUAL_POWER)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_CREATE_UTILITY_METERS)].description == {
        "suggested_value": True,
    }

    result = await process_config_flow(
        hass,
        result,
        {
            Step.VIRTUAL_POWER: {
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_ENTITY_ID: "light.test",
            },
            Step.FIXED: {
                **fixed_value_choice(CONF_POWER, 20),
            },
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.POWER_ADVANCED
    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert schema_keys[schema_keys.index(CONF_ENERGY_INTEGRATION_METHOD)].default() == ENERGY_INTEGRATION_METHOD_RIGHT
    assert schema_keys[schema_keys.index(CONF_IGNORE_UNAVAILABLE_STATE)].description == {"suggested_value": True}


async def test_sensor_is_created_without_providing_source_entity(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        user_input={
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_NAME: "My nice sensor",
        },
    )
    result = await set_virtual_power_configuration(
        hass,
        result,
        fixed_value_choice(CONF_POWER, 20),
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_nice_sensor_power")
    assert hass.states.get("sensor.my_nice_sensor_energy")


async def test_setup_twice_for_same_entity(hass: HomeAssistant) -> None:
    """
    Test that we can set up two virtual power sensors for the same entity.
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2684
    """
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        user_input={CONF_NAME: "My nice sensor", CONF_ENTITY_ID: "light.test"},
    )
    await set_virtual_power_configuration(
        hass,
        result,
        fixed_value_choice(CONF_POWER, 20),
    )

    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        user_input={CONF_NAME: "My nice sensor 2", CONF_ENTITY_ID: "light.test"},
    )
    await set_virtual_power_configuration(
        hass,
        result,
        fixed_value_choice(CONF_POWER, 20),
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_nice_sensor_power")
    assert hass.states.get("sensor.my_nice_sensor_2_power")
