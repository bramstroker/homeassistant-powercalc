from unittest.mock import AsyncMock

from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITIES, CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import mock_device_registry, mock_registry

from custom_components.powercalc import DiscoveryManager
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
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_discovery_flow,
    initialize_options_flow,
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

    assert hass.states.get("sensor.test_device_power").state == "0.82"

    hass.states.async_set("switch.b", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_device_power").state == "1.64"


async def test_discovery_flow_once_per_unique_device(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    hass.config.config_dir = get_test_config_dir()

    device_id = "abcdef"
    mock_device_registry(
        hass,
        {
            device_id: DeviceEntry(
                id=device_id,
                manufacturer="tp-link",
                model="HS300",
            ),
        },
    )

    entities: dict[str, RegistryEntry] = {}
    for i in range(6):
        entity_id = f"switch.test{i}"
        entry = RegistryEntry(
            id=entity_id,
            entity_id=entity_id,
            unique_id=f"{device_id}{i}",
            device_id=device_id,
            platform="switch",
        )
        entities[entity_id] = entry

    mock_registry(
        hass,
        entities,
    )

    discovery_manager = DiscoveryManager(hass, {})
    await discovery_manager.start_discovery()

    assert len(mock_flow_init.mock_calls) == 1


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.MULTI_SWITCH,
            CONF_MULTI_SWITCH: {CONF_POWER: 10, CONF_POWER_OFF: 40, CONF_ENTITIES: ["switch.a", "switch.b"]},
        },
    )

    result = await initialize_options_flow(hass, entry, Steps.MULTI_SWITCH)

    user_input = {CONF_POWER_OFF: 20, CONF_POWER: 5, CONF_ENTITIES: ["switch.a", "switch.c"]}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MULTI_SWITCH] == {CONF_POWER: 5, CONF_POWER_OFF: 20, CONF_ENTITIES: ["switch.a", "switch.c"]}
