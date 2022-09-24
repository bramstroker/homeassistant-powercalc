import logging

import pytest
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.utility_meter.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    ENERGY_KILO_WATT_HOUR,
    ENERGY_MEGA_WATT_HOUR,
    POWER_WATT,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import EntityRegistry
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_GROUP,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_HIDE_MEMBERS,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    CONF_SENSOR_TYPE,
    CONF_SUB_GROUPS,
    DOMAIN,
    DUMMY_ENTITY_ID,
    SERVICE_RESET_ENERGY,
    CalculationStrategy,
    SensorType,
    UnitPrefix,
)

from ..common import (
    create_input_boolean,
    create_input_booleans,
    create_mocked_virtual_power_sensor_entry,
    get_simple_fixed_config,
    run_powercalc_setup_yaml_config,
)


async def test_grouped_power_sensor(hass: HomeAssistant):
    ent_reg = er.async_get(hass)
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_UNIQUE_ID: "group_unique_id",
            CONF_CREATE_UTILITY_METERS: True,
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "input_boolean.test1",
                    CONF_UNIQUE_ID: "54552343242",
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 10.5},
                },
                get_simple_fixed_config("input_boolean.test2", 50),
            ],
        },
    )

    hass.states.async_set("input_boolean.test1", STATE_ON)
    hass.states.async_set("input_boolean.test2", STATE_ON)

    await hass.async_block_till_done()

    power_entry = ent_reg.async_get("sensor.testgroup_power")
    assert power_entry
    assert power_entry.unique_id == "group_unique_id"

    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state
    assert power_state.attributes.get("state_class") == SensorStateClass.MEASUREMENT
    assert power_state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.POWER
    assert power_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == POWER_WATT
    assert power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_power",
        "sensor.test2_power",
    }
    assert power_state.state == "60.50"

    energy_entry = ent_reg.async_get("sensor.testgroup_energy")
    assert energy_entry
    assert energy_entry.unique_id == "group_unique_id_energy"

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state
    assert energy_state.attributes.get("state_class") == SensorStateClass.TOTAL
    assert energy_state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY
    assert (
        energy_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_KILO_WATT_HOUR
    )
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_energy",
        "sensor.test2_energy",
    }


async def test_subgroups_from_config_entry(hass: HomeAssistant):
    config_entry_groupa = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test1_power"],
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.test1_energy"],
        },
    )
    config_entry_groupa.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_groupa.entry_id)
    await hass.async_block_till_done()

    config_entry_groupb = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupB",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test2_power"],
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.test2_energy"],
            CONF_SUB_GROUPS: [
                config_entry_groupa.entry_id,
                "464354354543",  # Non existing entry_id, should not break setup
            ],
        },
    )
    config_entry_groupb.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_groupb.entry_id)
    await hass.async_block_till_done()

    config_entry_groupc = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupC",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test3_power"],
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.test3_energy"],
            CONF_SUB_GROUPS: [config_entry_groupb.entry_id],
        },
    )

    config_entry_groupc.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_groupc.entry_id)
    await hass.async_block_till_done()

    groupa_power_state = hass.states.get("sensor.groupa_power")
    assert groupa_power_state
    assert groupa_power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_power",
    }
    groupa_energy_state = hass.states.get("sensor.groupa_energy")
    assert groupa_energy_state
    assert groupa_energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_energy",
    }

    groupb_power_state = hass.states.get("sensor.groupb_power")
    assert groupb_power_state
    assert groupb_power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_power",
        "sensor.test2_power",
    }
    groupb_energy_state = hass.states.get("sensor.groupb_energy")
    assert groupb_energy_state
    assert groupb_energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_energy",
        "sensor.test2_energy",
    }

    groupc_power_state = hass.states.get("sensor.groupc_power")
    assert groupc_power_state
    assert groupc_power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_power",
        "sensor.test2_power",
        "sensor.test3_power",
    }


async def test_entities_with_incompatible_unit_of_measurement_are_removed(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.NONE,
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "input_boolean.test1",
                    CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.NONE,
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 10.5},
                },
                {
                    CONF_ENTITY_ID: "input_boolean.test2",
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.KILO,
                    CONF_FIXED: {CONF_POWER: 50},
                },
            ],
        },
    )

    hass.states.async_set("input_boolean.test1", STATE_OFF)
    hass.states.async_set("input_boolean.test2", STATE_OFF)
    await hass.async_block_till_done()

    hass.states.async_set("input_boolean.test1", STATE_ON)
    hass.states.async_set("input_boolean.test2", STATE_ON)
    await hass.async_block_till_done()

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_energy",
    }

    assert "Removing this entity from the total sum" in caplog.text


async def test_reset_service(hass: HomeAssistant):
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1"),
                get_simple_fixed_config("input_boolean.test2"),
            ],
        },
    )

    # Set the individual entities to some initial values
    hass.states.async_set(
        "sensor.test1_energy", "0.8", {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
    )
    hass.states.async_set(
        "sensor.test2_energy", "1.2", {ATTR_UNIT_OF_MEASUREMENT: ENERGY_KILO_WATT_HOUR}
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_energy").state == "2.0000"

    # Reset the group sensor and underlying group members
    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESET_ENERGY,
        {
            ATTR_ENTITY_ID: "sensor.testgroup_energy",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_energy").state == "0.0000"
    assert hass.states.get("sensor.test1_energy").state == "0"
    assert hass.states.get("sensor.test2_energy").state == "0"


async def test_restore_state(hass: HomeAssistant):
    await create_input_boolean(hass, "test1")

    mock_restore_cache(
        hass,
        [
            State(
                "sensor.testgroup_energy",
                "0.5000",
            ),
        ],
    )

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1"),
            ],
        },
    )

    assert hass.states.get("sensor.testgroup_energy").state == "0.5000"


async def test_mega_watt_hour(hass: HomeAssistant):
    await create_input_boolean(hass, "test1")

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.MEGA,
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1"),
            ],
        },
    )

    state = hass.states.get("sensor.testgroup_energy")

    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == ENERGY_MEGA_WATT_HOUR


async def test_group_unavailable_when_members_unavailable(hass: HomeAssistant):
    """
    When any of the group members becomes unavailable the energy group should also be unavailable
    Group power sensor must only be unavailable when ALL group members are unavailable
    """
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1", 50),
                get_simple_fixed_config("input_boolean.test2", 50),
            ],
        },
    )

    hass.states.async_set("input_boolean.test1", STATE_UNAVAILABLE)
    hass.states.async_set("input_boolean.test2", STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state.state == STATE_UNAVAILABLE

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state.state == STATE_UNKNOWN

    hass.states.async_set("input_boolean.test1", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state.state != STATE_UNAVAILABLE

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state.state == STATE_UNAVAILABLE


async def test_hide_members(hass: HomeAssistant):
    entity_reg = er.async_get(hass)
    await create_input_booleans(hass, ["one", "two"])

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_HIDE_MEMBERS: True,
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "input_boolean.one",
                    CONF_UNIQUE_ID: "one",
                    CONF_FIXED: {CONF_POWER: 10},
                },
                {
                    CONF_ENTITY_ID: "input_boolean.two",
                    CONF_UNIQUE_ID: "two",
                    CONF_FIXED: {CONF_POWER: 20},
                },
            ],
        },
    )

    assert (
        entity_reg.async_get("sensor.one_power").hidden_by
        == er.RegistryEntryHider.INTEGRATION
    )
    assert (
        entity_reg.async_get("sensor.two_power").hidden_by
        == er.RegistryEntryHider.INTEGRATION
    )


async def test_unhide_members(hass: HomeAssistant):
    entity_reg = er.async_get(hass)
    entity_reg.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "abcdef",
        suggested_object_id="test_power",
        hidden_by=er.RegistryEntryHider.INTEGRATION,
    )
    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_HIDE_MEMBERS: False,
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: DUMMY_ENTITY_ID,
                    CONF_POWER_SENSOR_ID: "sensor.test_power",
                },
            ],
        },
    )

    assert entity_reg.async_get("sensor.test_power").hidden_by is None


async def test_members_are_unhiden_after_group_removed(
    hass: HomeAssistant, entity_reg: EntityRegistry
):
    entity_reg.async_get_or_create(
        "sensor", DOMAIN, "abcdef", suggested_object_id="test_power"
    )

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "MyGroup",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test_power"],
            CONF_HIDE_MEMBERS: True,
        },
        unique_id="group_unique_id",
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.mygroup_power")
    assert (
        entity_reg.async_get("sensor.test_power").hidden_by
        == er.RegistryEntryHider.INTEGRATION
    )

    # Remove the config entry
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert entity_reg.async_get("sensor.test_power").hidden_by is None

    assert not hass.states.get("sensor.mygroup_power")
    assert not entity_reg.async_get("sensor.mygroup_power")


async def test_group_utility_meter(hass: HomeAssistant, entity_reg: EntityRegistry):
    entity_reg.async_get_or_create(
        "sensor", DOMAIN, "abcdef", suggested_object_id="testgroup_power"
    )
    entity_reg.async_get_or_create(
        "sensor", DOMAIN, "abcdef_energy", suggested_object_id="testgroup_energy"
    )

    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_UNIQUE_ID: "abcdef",
            CONF_CREATE_UTILITY_METERS: True,
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1", 20),
                get_simple_fixed_config("input_boolean.test2", 50),
            ],
        },
    )

    utility_meter_state = hass.states.get("sensor.testgroup_energy_daily")
    assert utility_meter_state
    assert utility_meter_state.attributes.get("source") == "sensor.testgroup_energy"


async def test_include_config_entries_in_group(hass: HomeAssistant):
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UNIQUE_ID: "abcdef",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "VirtualSensor",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    group_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
            CONF_GROUP_MEMBER_SENSORS: [config_entry.entry_id],
            CONF_GROUP_POWER_ENTITIES: ["sensor.other_power"],
        },
    )

    group_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(group_config_entry.entry_id)
    await hass.async_block_till_done()

    group_power_state = hass.states.get("sensor.groupa_power")
    assert group_power_state
    assert group_power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.virtualsensor_power",
        "sensor.other_power",
    }

    group_energy_state = hass.states.get("sensor.groupa_energy")
    assert group_energy_state
    assert group_energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.virtualsensor_energy"
    }


async def test_add_virtual_power_sensor_to_group_on_creation(hass: HomeAssistant):
    """
    When creating a virtual power sensor using the config flow you can define a group you want to add it to
    Test that the new sensors are added to the existing group correctly
    """

    config_entry_sensor1 = await create_mocked_virtual_power_sensor_entry(
        hass, "VirtualSensor1", "xyz"
    )

    config_entry_group = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
            CONF_GROUP_MEMBER_SENSORS: [config_entry_sensor1.entry_id],
        },
    )
    config_entry_group.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_group.entry_id)
    await hass.async_block_till_done()

    config_entry_sensor2 = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "VirtualSensor2",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_UNIQUE_ID: "abc",
            CONF_GROUP: config_entry_group.entry_id,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )
    config_entry_sensor2.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_sensor2.entry_id)
    await hass.async_block_till_done()

    config_entry_group = hass.config_entries.async_get_entry(
        config_entry_group.entry_id
    )
    assert config_entry_group.data.get(CONF_GROUP_MEMBER_SENSORS) == [
        config_entry_sensor1.entry_id,
        config_entry_sensor2.entry_id,
    ]

    group_state = hass.states.get("sensor.groupa_power")
    assert group_state
    assert group_state.attributes.get("entities") == {
        "sensor.virtualsensor1_power",
        "sensor.virtualsensor2_power",
    }

    # Remove config entry from Home Assistant, and see if group is updated accordingly
    await hass.config_entries.async_remove(config_entry_sensor2.entry_id)
    await hass.async_block_till_done()

    config_entry_group = hass.config_entries.async_get_entry(
        config_entry_group.entry_id
    )
    assert config_entry_group.data.get(CONF_GROUP_MEMBER_SENSORS) == [
        config_entry_sensor1.entry_id,
    ]

    group_state = hass.states.get("sensor.groupa_power")
    assert group_state
    assert group_state.attributes.get("entities") == {
        "sensor.virtualsensor1_power",
    }


async def test_custom_naming_pattern(hass: HomeAssistant):
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1", 50),
                get_simple_fixed_config("input_boolean.test2", 50),
            ],
            CONF_ENERGY_SENSOR_NAMING: "{} - Energie",
        },
    )
    energy_state = hass.states.get("sensor.testgroup_energie")
    assert energy_state
    assert energy_state.name == "TestGroup - Energie"
    assert energy_state.attributes["friendly_name"] == "TestGroup - Energie"
