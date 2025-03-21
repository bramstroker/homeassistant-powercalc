from homeassistant import data_entry_flow
from homeassistant.const import ATTR_ENTITY_ID, CONF_ENTITY_ID, STATE_IDLE, STATE_PLAYING
from homeassistant.core import HomeAssistant

from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_AUTOSTART,
    CONF_MODE,
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_REPEAT,
    CONF_SENSOR_TYPE,
    CONF_STATE_TRIGGER,
    DOMAIN,
    SERVICE_GET_ACTIVE_PLAYBOOK,
    CalculationStrategy,
    SensorType,
)
from tests.common import get_test_config_dir, run_powercalc_setup
from tests.config_flow.common import (
    assert_default_virtual_power_entry_data,
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    set_virtual_power_configuration,
)


async def test_create_entry(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.PLAYBOOK)
    result = await set_virtual_power_configuration(
        hass,
        result,
        {
            CONF_PLAYBOOKS: {
                "playbook1": "test.csv",
                "playbook2": "test2.csv",
            },
            CONF_REPEAT: True,
            CONF_AUTOSTART: "playbook1",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.PLAYBOOK,
        result["data"],
        {
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook1": "test.csv",
                    "playbook2": "test2.csv",
                },
                CONF_REPEAT: True,
                CONF_AUTOSTART: "playbook1",
            },
        },
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_options_flow(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.PLAYBOOK,
            CONF_PLAYBOOK: {
                CONF_PLAYBOOKS: {
                    "playbook1": "test.csv",
                    "playbook2": "test2.csv",
                },
                CONF_REPEAT: False,
                CONF_AUTOSTART: "playbook1",
            },
        },
    )

    result = await initialize_options_flow(hass, entry, Step.PLAYBOOK)

    user_input = {
        CONF_PLAYBOOKS: {
            "playbook1": "test.csv",
            "playbook2": "test2.csv",
        },
        CONF_REPEAT: True,
        CONF_AUTOSTART: "playbook2",
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_PLAYBOOK][CONF_REPEAT]
    assert entry.data[CONF_PLAYBOOK][CONF_AUTOSTART] == "playbook2"


async def test_playbooks_mandatory(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.PLAYBOOK)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_REPEAT: True,
            CONF_AUTOSTART: "playbook1",
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "playbook_mandatory"}


async def test_state_trigger(hass: HomeAssistant) -> None:
    hass.config.config_dir = get_test_config_dir()
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.PLAYBOOK,
        {CONF_ENTITY_ID: "media_player.test"},
    )
    await set_virtual_power_configuration(
        hass,
        result,
        {
            CONF_PLAYBOOKS: {
                "playbook1": "test.csv",
                "playbook2": "test2.csv",
            },
            CONF_STATE_TRIGGER: {
                STATE_IDLE: "playbook1",
                STATE_PLAYING: "playbook2",
            },
        },
    )

    await run_powercalc_setup(hass, {})

    hass.states.async_set("media_player.test", STATE_IDLE)
    await hass.async_block_till_done()

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_ACTIVE_PLAYBOOK,
        {ATTR_ENTITY_ID: "sensor.test_power"},
        blocking=True,
        return_response=True,
    )

    data = next(iter(result.values()))
    assert data["id"] == "playbook1"
