import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES, CONF_ENTITY_ID, CONF_NAME, CONF_SENSOR_TYPE, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.helpers.selector import SelectSelector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import SensorType
from custom_components.powercalc.const import (
    CONF_AREA,
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_HIDE_MEMBERS,
    CONF_MODE,
    CONF_POWER,
    CONF_STATES_POWER,
    CONF_SUB_GROUPS,
    DOMAIN,
    CalculationStrategy,
)
from custom_components.test.light import MockLight
from tests.common import create_mock_light_entity, create_mocked_virtual_power_sensor_entry
from tests.config_flow.common import (
    DEFAULT_UNIQUE_ID,
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    select_sensor_type,
    set_virtual_power_configuration,
)


async def test_create_group_entry(hass: HomeAssistant) -> None:
    result = await select_sensor_type(hass, SensorType.GROUP)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power", "sensor.bedroom1_power"],
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "My group sensor",
        CONF_HIDE_MEMBERS: False,
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power", "sensor.bedroom1_power"],
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_CREATE_UTILITY_METERS: False,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_group_sensor_power")


async def test_create_group_entry_without_unique_id(hass: HomeAssistant) -> None:
    result = await select_sensor_type(hass, SensorType.GROUP)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power"],
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "My group sensor",
        CONF_HIDE_MEMBERS: False,
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power"],
        CONF_UNIQUE_ID: "My group sensor",
        CONF_CREATE_UTILITY_METERS: False,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_group_sensor_power")


async def test_group_include_area(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
    area_reg: AreaRegistry,
) -> None:
    # Create light entity and add to group My area
    light = MockLight("test")
    await create_mock_light_entity(hass, light)
    area = area_reg.async_get_or_create("My area")
    entity_reg.async_update_entity(light.entity_id, area_id=area.id)

    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        {CONF_ENTITY_ID: "light.test"},
    )
    await set_virtual_power_configuration(
        hass,
        result,
        {CONF_STATES_POWER: {"playing": 1.8}},
    )

    result = await select_sensor_type(hass, SensorType.GROUP)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_AREA: area.id,
        CONF_CREATE_UTILITY_METERS: True,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "My group sensor",
        CONF_HIDE_MEMBERS: False,
        CONF_AREA: area.id,
        CONF_UNIQUE_ID: "My group sensor",
        CONF_CREATE_UTILITY_METERS: True,
    }
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.my_group_sensor_power")
    assert power_state
    assert power_state.attributes.get(CONF_ENTITIES) == {"sensor.test_power"}

    energy_state = hass.states.get("sensor.my_group_sensor_energy")
    assert energy_state
    assert energy_state.attributes.get(CONF_ENTITIES) == {"sensor.test_energy"}

    assert hass.states.get("sensor.my_group_sensor_energy_daily")


async def test_can_unset_area(hass: HomeAssistant, area_reg: AreaRegistry) -> None:
    area_reg.async_get_or_create("My area")
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abcdefg",
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_AREA: "My area",
        },
        title="TestArea",
    )
    config_entry.add_to_hass(hass)

    updated_entry = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert updated_entry.data == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_AREA: "My area",
    }

    result = await initialize_options_flow(hass, config_entry)

    user_input = {}
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )
    updated_entry = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert updated_entry.data == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_HIDE_MEMBERS: False,
    }


async def test_can_select_existing_powercalc_entry_as_group_member(
    hass: HomeAssistant,
) -> None:
    """
    Test if we can select previously created virtual power config entries as the group member.
    Only entries with a unique ID must be selectable
    """

    config_entry_1 = await create_mocked_virtual_power_sensor_entry(
        hass,
        "VirtualPower1",
        "abcdef",
    )
    config_entry_2 = await create_mocked_virtual_power_sensor_entry(
        hass,
        "VirtualPower2",
        None,
    )
    config_entry_3 = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abcdefg",
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "abcdefg",
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
        title="VirtualPower3",
    )
    config_entry_3.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_3.entry_id)
    await hass.async_block_till_done()

    result = await select_sensor_type(hass, SensorType.GROUP)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    data_schema: vol.Schema = result["data_schema"]
    select: SelectSelector = data_schema.schema[CONF_GROUP_MEMBER_SENSORS]
    options = select.config["options"]
    assert {"value": config_entry_1.entry_id, "label": "VirtualPower1"} in options
    assert {"value": config_entry_2.entry_id, "label": "VirtualPower2"} not in options

    user_input = {
        CONF_NAME: "My group sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_GROUP_MEMBER_SENSORS: [config_entry_1.entry_id],
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "My group sensor",
        CONF_HIDE_MEMBERS: False,
        CONF_GROUP_MEMBER_SENSORS: [config_entry_1.entry_id],
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_CREATE_UTILITY_METERS: False,
    }


async def test_group_error_mandatory(hass: HomeAssistant) -> None:
    result = await select_sensor_type(hass, SensorType.GROUP)
    user_input = {CONF_NAME: "My group sensor", CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]
    assert result["errors"]["base"] == "group_mandatory"


async def test_subgroup_selector(hass: HomeAssistant) -> None:
    # Create two existing group config entries
    group1_entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "Group1",
            CONF_SENSOR_TYPE: SensorType.GROUP,
        },
    )
    group2_entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "Group2",
            CONF_SENSOR_TYPE: SensorType.GROUP,
        },
    )

    # Initialize a new config flow
    result = await select_sensor_type(hass, SensorType.GROUP)

    # Assert the two existing groups can be selected as subgroup
    data_schema: vol.Schema = result["data_schema"]
    sub_group_selector: SelectSelector = data_schema.schema[CONF_SUB_GROUPS]
    options = sub_group_selector.config["options"]
    assert options == [
        {"label": "Group1", "value": group1_entry.entry_id},
        {"label": "Group2", "value": group2_entry.entry_id},
    ]

    # Create the new group
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Group3",
            CONF_SUB_GROUPS: [group1_entry.entry_id, group2_entry.entry_id],
        },
    )

    # Initialize the options flow for the newly created group
    new_entry: ConfigEntry = result["result"]
    result = await hass.config_entries.options.async_init(
        new_entry.entry_id,
        data=None,
    )

    # Assert that the group itself is not selectable as subgroup
    data_schema: vol.Schema = result["data_schema"]
    sub_group_selector: SelectSelector = data_schema.schema[CONF_SUB_GROUPS]
    options = sub_group_selector.config["options"]
    assert options == [
        {"label": "Group1", "value": group1_entry.entry_id},
        {"label": "Group2", "value": group2_entry.entry_id},
    ]


async def test_group_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "Kitchen",
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_POWER_ENTITIES: ["sensor.fridge_power"],
        },
    )

    result = await initialize_options_flow(hass, entry)

    new_entities = ["sensor.fridge_power", "sensor.kitchen_lights_power"]
    user_input = {CONF_GROUP_POWER_ENTITIES: new_entities}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_GROUP_POWER_ENTITIES] == new_entities
