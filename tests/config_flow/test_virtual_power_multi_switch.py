from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITIES, CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.config_flow import Steps
from custom_components.powercalc.const import (
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTI_SWITCH,
    CONF_POWER,
    CONF_POWER_OFF,
    CONF_SENSOR_TYPE,
    CalculationStrategy,
    SensorType,
)
from tests.common import get_test_config_dir
from tests.config_flow.common import (
    DEFAULT_UNIQUE_ID,
    goto_virtual_power_strategy_step,
    initialize_discovery_flow,
    set_virtual_power_configuration,
)
from tests.conftest import MockEntityWithModel


async def test_create_multi_switch_sensor_entry(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.MULTI_SWITCH, {CONF_NAME: "test"})
    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_ENTITIES: ["switch.a", "switch.b"], CONF_POWER: 0.8, CONF_POWER_OFF: 0.5},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    entry_data = result["data"]
    assert entry_data[CONF_SENSOR_TYPE] == SensorType.VIRTUAL_POWER
    assert entry_data[CONF_MODE] == CalculationStrategy.MULTI_SWITCH
    assert entry_data[CONF_MULTI_SWITCH] == {CONF_ENTITIES: ["switch.a", "switch.b"], CONF_POWER: 0.8, CONF_POWER_OFF: 0.5}

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")

    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get("sensor.test_power")
    assert entry


async def test_discovery_flow(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    hass.config.config_dir = get_test_config_dir()
    manufacturer = "tp-link"
    model = "HS300"
    mock_entity_with_model_information(
        "switch.test",
        manufacturer,
        model,
        unique_id=DEFAULT_UNIQUE_ID,
    )

    source_entity = await create_source_entity("switch.test", hass)
    result = await initialize_discovery_flow(hass, source_entity, confirm_autodiscovered_model=True)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Steps.MULTI_SWITCH

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITIES: ["switch.a", "switch.b"]},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ENTITY_ID: "switch.test",
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MANUFACTURER: manufacturer,
        CONF_MODEL: model,
        CONF_NAME: "test",
        CONF_UNIQUE_ID: f"pc_{DEFAULT_UNIQUE_ID}",
        CONF_MULTI_SWITCH: {
            CONF_ENTITIES: ["switch.a", "switch.b"],
        },
    }

    assert hass.states.get("sensor.test_device_power")

    hass.states.async_set("switch.a", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_device_power").state == "2.16"
