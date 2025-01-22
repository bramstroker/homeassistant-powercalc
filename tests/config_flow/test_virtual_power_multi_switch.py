from unittest.mock import AsyncMock

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.const import CONF_DEVICE, CONF_ENTITIES, CONF_ENTITY_ID, CONF_NAME, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.selector import EntitySelector
from pytest_homeassistant_custom_component.common import mock_device_registry, mock_registry

from custom_components.powercalc import DiscoveryManager
from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_AVAILABILITY_ENTITY,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTI_SWITCH,
    CONF_POWER,
    CONF_POWER_OFF,
    CONF_SENSOR_TYPE,
    DUMMY_ENTITY_ID,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.power_profile.factory import get_power_profile
from custom_components.powercalc.power_profile.library import ModelInfo
from tests.common import get_test_config_dir, run_powercalc_setup
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
    device_entry = mock_device_with_switches(hass, 2)

    result = await initialize_device_discovery_flow(hass, device_entry)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.AVAILABILITY_ENTITY

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AVAILABILITY_ENTITY: "switch.test1"},
    )

    assert result["step_id"] == Step.MULTI_SWITCH

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITIES: ["switch.test1", "switch.test2"]},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_AVAILABILITY_ENTITY: "switch.test1",
        CONF_ENTITY_ID: DUMMY_ENTITY_ID,
        CONF_DEVICE: device_entry.id,
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MANUFACTURER: "test",
        CONF_MODEL: "multi_switch",
        CONF_NAME: "Test",
        CONF_MULTI_SWITCH: {
            CONF_ENTITIES: ["switch.test1", "switch.test2"],
        },
    }

    assert hass.states.get("sensor.test_power")

    hass.states.async_set("switch.test1", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "1.22"

    hass.states.async_set("switch.test2", STATE_ON)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "1.95"


async def test_switch_entities_automatically_populated_from_device(hass: HomeAssistant) -> None:
    """When setting up multi switch, the switch entities should be automatically populated from the device."""
    hass.config.config_dir = get_test_config_dir()
    device_entry = mock_device_with_switches(hass, 4)

    result = await initialize_device_discovery_flow(hass, device_entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AVAILABILITY_ENTITY: "switch.test1"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MULTI_SWITCH

    expected_entities = ["switch.test1", "switch.test2", "switch.test3", "switch.test4"]

    data_schema: vol.Schema = result["data_schema"]
    select: EntitySelector = data_schema.schema[CONF_ENTITIES]
    assert select.config["include_entities"] == expected_entities

    schema_keys = list(data_schema.schema.keys())
    assert schema_keys[schema_keys.index(CONF_ENTITIES)].default() == expected_entities


async def test_discovery_flow_once_per_unique_device(
    hass: HomeAssistant,
    mock_flow_init: AsyncMock,
) -> None:
    hass.config.config_dir = get_test_config_dir()

    mock_device_with_switches(hass, 6)

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

    result = await initialize_options_flow(hass, entry, Step.MULTI_SWITCH)

    user_input = {CONF_POWER_OFF: 20, CONF_POWER: 5, CONF_ENTITIES: ["switch.a", "switch.c"]}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MULTI_SWITCH] == {CONF_POWER: 5, CONF_POWER_OFF: 20, CONF_ENTITIES: ["switch.a", "switch.c"]}


async def test_regression_2612(hass: HomeAssistant, mock_entity_with_model_information: MockEntityWithModel) -> None:
    """
    See #2612
    When the source entity had manufacturer and model information the multi switch setup would fail
    And raise error "Model not found in library" in the logs
    """

    mock_entity_with_model_information(
        "switch.test",
        "_TZ3000_u3oupgdy",
        "TS0004",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.MULTI_SWITCH,
            CONF_MULTI_SWITCH: {
                CONF_POWER: 10,
                CONF_POWER_OFF: 40,
                CONF_ENTITIES: ["switch.a", "switch.b"],
            },
            CONF_NAME: "Foo bar",
        },
    )

    await run_powercalc_setup(hass, {})

    assert hass.states.get("sensor.foo_bar_power")
    assert hass.states.get("sensor.foo_bar_energy")


async def test_light_switches_selectable(hass: HomeAssistant) -> None:
    """
    Some integrations allow you to change the type of a switch to light.
    Make sure that light entities are also selectable in the multi switch setup
    """
    hass.config.config_dir = get_test_config_dir()

    device_id = "abcdef"
    device_entry = DeviceEntry(
        id=device_id,
        manufacturer="test",
        model="multi_switch",
        name="Test",
    )
    mock_device_registry(
        hass,
        {
            device_id: device_entry,
        },
    )
    mock_registry(
        hass,
        {
            "switch.test1": RegistryEntry(
                id="switch.test1",
                entity_id="switch.test1",
                unique_id=f"{device_id}1",
                device_id=device_id,
                platform="switch",
            ),
            "light.test2": RegistryEntry(
                id="light.test2",
                entity_id="light.test2",
                unique_id=f"{device_id}2",
                device_id=device_id,
                platform="light",
            ),
        },
    )

    result = await initialize_device_discovery_flow(hass, device_entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AVAILABILITY_ENTITY: "switch.test1"},
    )

    data_schema: vol.Schema = result["data_schema"]
    entities_select: EntitySelector = data_schema.schema["entities"]
    options = entities_select.config["include_entities"]
    assert options == ["switch.test1", "light.test2"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITIES: ["switch.test1", "light.test2"]},
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def initialize_device_discovery_flow(hass: HomeAssistant, device_entry: DeviceEntry) -> FlowResult:
    source_entity = SourceEntity(
        object_id=device_entry.name,
        name=device_entry.name,
        entity_id=DUMMY_ENTITY_ID,
        domain="sensor",
        device_entry=device_entry,
    )

    power_profiles = [
        await get_power_profile(
            hass,
            {},
            ModelInfo(device_entry.manufacturer, device_entry.model),
        ),
    ]
    return await initialize_discovery_flow(
        hass,
        source_entity,
        power_profiles,
        confirm_autodiscovered_model=True,
    )


def mock_device_with_switches(hass: HomeAssistant, num_switches: int = 2, manufacturer: str = "test", model: str = "multi_switch") -> DeviceEntry:
    device_id = "abcdef"
    device_entry = DeviceEntry(
        id=device_id,
        manufacturer=manufacturer,
        model=model,
        name="Test",
    )
    mock_device_registry(
        hass,
        {
            device_id: device_entry,
        },
    )

    entities: dict[str, RegistryEntry] = {}
    for i in range(num_switches):
        entity_id = f"switch.test{i + 1}"
        entry = RegistryEntry(
            id=entity_id,
            entity_id=entity_id,
            unique_id=f"{device_id}{i + 1}",
            device_id=device_id,
            platform="switch",
        )
        entities[entity_id] = entry

    mock_registry(
        hass,
        entities,
    )

    return device_entry
