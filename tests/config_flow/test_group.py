import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.utility_meter.const import DAILY
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_SENSOR_TYPE,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import EntityRegistry, RegistryEntry
from homeassistant.helpers.selector import SelectSelector
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_device_registry, mock_registry

from custom_components.powercalc import SensorType, async_migrate_entry
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_AREA,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
    CONF_FIXED,
    CONF_FORCE_CALCULATE_GROUP_ENERGY,
    CONF_GROUP,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_ENERGY_START_AT_ZERO,
    CONF_GROUP_MEMBER_DEVICES,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_GROUP_TYPE,
    CONF_HIDE_MEMBERS,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_MODE,
    CONF_NEW_GROUP,
    CONF_POWER,
    CONF_STATES_POWER,
    CONF_SUB_GROUPS,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    ENTRY_DATA_ENERGY_ENTITY,
    CalculationStrategy,
    GroupType,
)
from custom_components.powercalc.sensors.group.config_entry_utils import add_to_associated_groups
from custom_components.test.light import MockLight
from tests.common import (
    create_mock_light_entity,
    create_mocked_virtual_power_sensor_entry,
    run_powercalc_setup,
    setup_config_entry,
)
from tests.config_flow.common import (
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    select_menu_item,
    set_virtual_power_configuration,
)


async def test_create_group_entry(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
    user_input = {
        CONF_NAME: "My group sensor",
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
        CONF_FORCE_CALCULATE_GROUP_ENERGY: False,
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power", "sensor.bedroom1_power"],
        CONF_GROUP_TYPE: GroupType.CUSTOM,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_GROUP_ENERGY_START_AT_ZERO: True,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_group_sensor_power")


async def test_create_group_entry_without_unique_id(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
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
        CONF_GROUP_TYPE: GroupType.CUSTOM,
        CONF_FORCE_CALCULATE_GROUP_ENERGY: False,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_GROUP_ENERGY_START_AT_ZERO: True,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_group_sensor_power")


async def test_create_energy_sensor_enabled(hass: HomeAssistant) -> None:
    """
    Test if the energy sensor is created when `create_energy_sensors` is disabled on the global level,
    but enabled for the config entry
    """
    await run_powercalc_setup(hass, {}, {CONF_CREATE_ENERGY_SENSORS: False})

    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_GROUP_POWER_ENTITIES: ["sensor.balcony_power"],
        CONF_GROUP_ENERGY_ENTITIES: ["sensor.balcony_energy"],
        CONF_CREATE_ENERGY_SENSOR: True,
    }
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_group_sensor_power")
    assert hass.states.get("sensor.my_group_sensor_energy")


async def test_add_device_members_to_group(hass: HomeAssistant) -> None:
    mock_device_registry(
        hass,
        {
            "my-device": DeviceEntry(
                id="my-device",
                name="My device",
                manufacturer="Mock",
                model="Device",
            ),
        },
    )

    mock_registry(
        hass,
        {
            "sensor.balcony_power": RegistryEntry(
                entity_id="sensor.balcony_power",
                unique_id="1111",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
                device_id="my-device",
            ),
            "sensor.balcony_energy": RegistryEntry(
                entity_id="sensor.balcony_energy",
                unique_id="2222",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
                device_id="my-device",
            ),
        },
    )

    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_GROUP_MEMBER_DEVICES: ["my-device"],
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
        CONF_FORCE_CALCULATE_GROUP_ENERGY: False,
        CONF_GROUP_MEMBER_DEVICES: ["my-device"],
        CONF_GROUP_TYPE: GroupType.CUSTOM,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_GROUP_ENERGY_START_AT_ZERO: True,
    }

    hass.states.async_set("sensor.balcony_power", 5)
    hass.states.async_set("sensor.balcony_energy", 5)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.my_group_sensor_power")
    assert power_state
    assert power_state.attributes.get(CONF_ENTITIES) == {"sensor.balcony_power"}

    energy_state = hass.states.get("sensor.my_group_sensor_energy")
    assert energy_state
    assert energy_state.attributes.get(CONF_ENTITIES) == {"sensor.balcony_energy"}


async def test_group_include_area(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
    area_registry: AreaRegistry,
) -> None:
    # Create light entity and add to group My area
    light = MockLight("test")
    await create_mock_light_entity(hass, light)
    area = area_registry.async_get_or_create("My area")
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

    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_AREA: area.id,
        CONF_CREATE_UTILITY_METERS: True,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    # Submit utility_meter_options step with default settings
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_GROUP_TYPE: GroupType.CUSTOM,
        CONF_NAME: "My group sensor",
        CONF_HIDE_MEMBERS: False,
        CONF_FORCE_CALCULATE_GROUP_ENERGY: False,
        CONF_AREA: area.id,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: True,
        CONF_UTILITY_METER_OFFSET: 0,
        CONF_UTILITY_METER_NET_CONSUMPTION: False,
        CONF_UTILITY_METER_TARIFFS: [],
        CONF_UTILITY_METER_TYPES: [DAILY],
        CONF_GROUP_ENERGY_START_AT_ZERO: True,
    }

    hass.states.async_set("sensor.test_power", 5)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.my_group_sensor_power")
    assert power_state
    assert power_state.attributes.get(CONF_ENTITIES) == {"sensor.test_power"}

    energy_state = hass.states.get("sensor.my_group_sensor_energy")
    assert energy_state

    assert hass.states.get("sensor.my_group_sensor_energy_daily")


async def test_can_unset_area(hass: HomeAssistant, area_registry: AreaRegistry) -> None:
    area_registry.async_get_or_create("My area")
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abcdefg",
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestArea",
            CONF_AREA: "My area",
        },
        title="TestArea",
    )
    config_entry.add_to_hass(hass)

    updated_entry = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert updated_entry.data == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "TestArea",
        CONF_AREA: "My area",
    }

    result = await initialize_options_flow(hass, config_entry, Step.GROUP_CUSTOM)

    user_input = {}
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )
    updated_entry = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert updated_entry.data == {
        ENTRY_DATA_ENERGY_ENTITY: "sensor.testarea_energy",
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "TestArea",
        CONF_FORCE_CALCULATE_GROUP_ENERGY: False,
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        CONF_HIDE_MEMBERS: False,
    }


async def test_include_area_powercalc_only(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    area = area_registry.async_get_or_create("My area")
    mock_registry(
        hass,
        {
            "switch.switch": RegistryEntry(
                entity_id="switch.switch",
                unique_id="1111",
                platform="switch",
                area_id=area.id,
            ),
            "sensor.existing_power": RegistryEntry(
                entity_id="sensor.existing_power",
                unique_id="3333",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
                area_id=area.id,
            ),
        },
    )

    await setup_config_entry(hass, {CONF_ENTITY_ID: "switch.switch", CONF_NAME: "Test", CONF_FIXED: {CONF_POWER: 5}})

    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
    user_input = {
        CONF_NAME: "My group sensor",
        CONF_AREA: area.id,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: False,
        CONF_CREATE_UTILITY_METERS: False,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert not result["data"][CONF_INCLUDE_NON_POWERCALC_SENSORS]

    hass.states.async_set("sensor.test_power", 5)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.my_group_sensor_power")
    assert power_state
    assert power_state.attributes.get(CONF_ENTITIES) == {"sensor.test_power"}


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
            CONF_ENTITY_ID: "sensor.dummy",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
        title="VirtualPower3",
    )
    config_entry_3.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_3.entry_id)
    await hass.async_block_till_done()

    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    data_schema: vol.Schema = result["data_schema"]
    select: SelectSelector = data_schema.schema[CONF_GROUP_MEMBER_SENSORS]
    options = select.config["options"]
    assert len(options) == 2
    assert {"value": config_entry_1.entry_id, "label": "VirtualPower1"} in options
    assert {"value": config_entry_2.entry_id, "label": "VirtualPower2"} not in options

    user_input = {
        CONF_NAME: "My group sensor",
        CONF_GROUP_MEMBER_SENSORS: [config_entry_1.entry_id],
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_GROUP_TYPE: GroupType.CUSTOM,
        CONF_NAME: "My group sensor",
        CONF_FORCE_CALCULATE_GROUP_ENERGY: False,
        CONF_HIDE_MEMBERS: False,
        CONF_GROUP_MEMBER_SENSORS: [config_entry_1.entry_id],
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_GROUP_ENERGY_START_AT_ZERO: True,
    }


async def test_real_power_entry_selectable_as_group_member(
    hass: HomeAssistant,
) -> None:
    """
    Test if we can select both virtual power sensor and real power sensor into the group,
    and the total power is calculated correctly
    """

    config_entry_1 = await create_mocked_virtual_power_sensor_entry(
        hass,
        "VirtualPower1",
        "abcdef",
    )
    config_entry_2 = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abcdefg",
        data={
            CONF_SENSOR_TYPE: SensorType.REAL_POWER,
            CONF_ENTITY_ID: "sensor.real_power",
        },
        title="RealPower1",
    )
    config_entry_2.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_2.entry_id)
    await hass.async_block_till_done()

    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    data_schema: vol.Schema = result["data_schema"]
    select: SelectSelector = data_schema.schema[CONF_GROUP_MEMBER_SENSORS]
    options = select.config["options"]
    assert len(options) == 2
    assert {"value": config_entry_1.entry_id, "label": "VirtualPower1"} in options
    assert {"value": config_entry_2.entry_id, "label": "RealPower1"} in options

    user_input = {
        CONF_NAME: "My group sensor",
        CONF_GROUP_MEMBER_SENSORS: [config_entry_1.entry_id, config_entry_2.entry_id],
    }
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    hass.states.async_set("sensor.real_power", "25.00")
    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.my_group_sensor_power")
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.virtualpower1_power", "sensor.real_power"}
    assert group_state
    assert group_state.state == "75.00"


async def test_group_error_mandatory(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
    user_input = {CONF_NAME: "My group sensor"}
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
            CONF_GROUP_TYPE: GroupType.CUSTOM,
        },
    )
    group2_entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "Group2",
            CONF_SENSOR_TYPE: SensorType.GROUP,
        },
    )
    create_mock_entry(
        hass,
        {
            CONF_NAME: "Group3",
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_TYPE: GroupType.DOMAIN,
        },
    )

    # Initialize a new config flow
    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)

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
    result = await initialize_options_flow(hass, new_entry, Step.GROUP_CUSTOM)

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
            CONF_CREATE_UTILITY_METERS: False,
            CONF_GROUP_POWER_ENTITIES: ["sensor.fridge_power"],
        },
    )

    result = await initialize_options_flow(hass, entry, Step.BASIC_OPTIONS)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_CREATE_UTILITY_METERS: True},
    )

    result = await initialize_options_flow(hass, entry, Step.GROUP_CUSTOM)

    new_entities = ["sensor.fridge_power", "sensor.kitchen_lights_power"]
    user_input = {CONF_GROUP_POWER_ENTITIES: new_entities}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_GROUP_POWER_ENTITIES] == new_entities
    assert entry.data[CONF_CREATE_UTILITY_METERS]


async def test_field_defaults_from_global_powercalc_config(hass: HomeAssistant) -> None:
    """Check that the toggle is default disabled when we set include_non_powercalc_sensors globally to false"""
    await run_powercalc_setup(hass, {}, {CONF_INCLUDE_NON_POWERCALC_SENSORS: False})

    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    schema_keys: list[vol.Optional] = list(result["data_schema"].schema.keys())
    assert not schema_keys[schema_keys.index(CONF_INCLUDE_NON_POWERCALC_SENSORS)].default()


async def test_migrate_config_entry_from_version_2(hass: HomeAssistant) -> None:
    """Test migration of a group sensor entry to version 3. Should add `create_energy_sensor` field."""
    mock_entry = MockConfigEntry(domain=DOMAIN, data={CONF_SENSOR_TYPE: SensorType.GROUP}, version=2)
    mock_entry.add_to_hass(hass)
    await async_migrate_entry(hass, mock_entry)
    hass.config_entries.async_get_entry(mock_entry.entry_id)
    assert mock_entry.version == 4
    assert mock_entry.data.get(CONF_CREATE_ENERGY_SENSOR)


async def test_create_group_on_demand_from_virtual_power_flow(hass: HomeAssistant) -> None:
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="abcdefg",
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_TYPE: GroupType.CUSTOM,
        },
        title="TestGroup",
    )
    config_entry.add_to_hass(hass)

    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        user_input={
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_NAME: "My power sensor",
        },
    )
    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_POWER: 20},
        group_options={CONF_NEW_GROUP: "New group"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    assert hass.states.get("sensor.new_group_power")
    assert hass.states.get("sensor.new_group_energy")

    config_entry = hass.config_entries.async_get_entry(result["result"].entry_id)

    # Prevent regression by checking if group is not already created and added twice, see #2366
    await add_to_associated_groups(hass, config_entry)
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 3


async def test_no_group_created_when_group_null(hass: HomeAssistant) -> None:
    """
    Previously a group was created with the name "None" when the group field was set to null.
    Prevent regression by checking if the group field is null and not creating a group in that case.
    See https://github.com/bramstroker/homeassistant-powercalc/issues/2281
    """
    await setup_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.my_light",
            CONF_NAME: "Some light",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_GROUP: None,
        },
        "abc",
        "Some light",
    )

    assert not hass.states.get("sensor.none_power")


async def test_domain_group_flow(hass: HomeAssistant) -> None:
    """Test the group flow for a domain."""
    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_DOMAIN)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    user_input = {
        CONF_NAME: "My group sensor",
        CONF_DOMAIN: Platform.LIGHT,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_GROUP_TYPE: GroupType.DOMAIN,
        CONF_NAME: "My group sensor",
        CONF_DOMAIN: Platform.LIGHT,
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
    }
    config_entry: ConfigEntry = result["result"]

    power_state = hass.states.get("sensor.my_group_sensor_power")
    assert power_state

    result = await hass.config_entries.options.async_init(
        config_entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert Step.BASIC_OPTIONS in result["menu_options"]
    assert Step.GROUP_CUSTOM not in result["menu_options"]
    assert Step.UTILITY_METER_OPTIONS not in result["menu_options"]
