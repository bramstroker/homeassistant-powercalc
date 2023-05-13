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
    POWER_WATT,
    STATE_ON,
    STATE_UNAVAILABLE,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import EntityRegistry
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_IS_GROUP,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_GROUP,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_HIDE_MEMBERS,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_POWER,
    CONF_SUB_GROUPS,
    CONF_UNAVAILABLE_POWER,
    DOMAIN,
    DUMMY_ENTITY_ID,
    SERVICE_RESET_ENERGY,
    CalculationStrategy,
    SensorType,
    UnitPrefix,
)
from custom_components.powercalc.sensors.group import PreviousStateStore
from tests.common import (
    create_input_boolean,
    create_input_booleans,
    create_mocked_virtual_power_sensor_entry,
    get_simple_fixed_config,
    run_powercalc_setup,
)


async def test_grouped_power_sensor(hass: HomeAssistant) -> None:
    ent_reg = er.async_get(hass)
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup(
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
        energy_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        == UnitOfEnergy.KILO_WATT_HOUR
    )
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_energy",
        "sensor.test2_energy",
    }


async def test_subgroups_from_config_entry(hass: HomeAssistant) -> None:
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


async def test_reset_service(hass: HomeAssistant) -> None:
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup(
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
        "sensor.test1_energy",
        "0.8",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.test2_energy",
        "1.2",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
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

    hass.states.async_set(
        "sensor.test2_energy",
        "0.5",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_energy").state == "0.5000"


async def test_restore_state(hass: HomeAssistant) -> None:
    await create_input_boolean(hass, "test1")

    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(
                    "sensor.testgroup_energy",
                    "0.5000",
                ),
                {"native_unit_of_measurement": None, "native_value": 0.5},
            ),
        ),
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1"),
            ],
        },
    )

    assert hass.states.get("sensor.testgroup_energy").state == "0.5000"


async def test_mega_watt_hour(hass: HomeAssistant) -> None:
    await create_input_boolean(hass, "test1")

    await run_powercalc_setup(
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

    assert state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfEnergy.MEGA_WATT_HOUR


async def test_group_unavailable_when_members_unavailable(hass: HomeAssistant) -> None:
    """
    When any of the group members becomes unavailable the energy group should also be unavailable
    Group power sensor must only be unavailable when ALL group members are unavailable
    """
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup(
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
    assert energy_state.state == STATE_UNAVAILABLE

    hass.states.async_set("input_boolean.test1", STATE_ON)
    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state.state != STATE_UNAVAILABLE

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state.state == STATE_UNAVAILABLE


async def test_energy_group_available_when_members_temporarily_unavailable(
    hass: HomeAssistant,
) -> None:
    """
    When any of the member sensors of a grouped energy sensor become unavailable,
     we try to use the last know correct state value of the member sensor
    """
    await create_input_booleans(hass, ["test1", "test2"])
    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1", 50),
                get_simple_fixed_config("input_boolean.test2", 50),
            ],
        },
    )

    hass.states.async_set("sensor.test1_energy", "1.0")
    hass.states.async_set("sensor.test2_energy", "2.0")
    await hass.async_block_till_done()

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state.state == "3.0000"

    hass.states.async_set("sensor.test1_energy", STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state.state == "3.0000"

    hass.states.async_set("sensor.test2_energy", "2.2")
    await hass.async_block_till_done()

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state.state == "3.2000"


async def test_hide_members(hass: HomeAssistant) -> None:
    entity_reg = er.async_get(hass)
    await create_input_booleans(hass, ["one", "two"])

    await run_powercalc_setup(
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


async def test_unhide_members(hass: HomeAssistant) -> None:
    entity_reg = er.async_get(hass)
    entity_reg.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "abcdef",
        suggested_object_id="test_power",
        hidden_by=er.RegistryEntryHider.INTEGRATION,
    )
    await hass.async_block_till_done()

    await run_powercalc_setup(
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


async def test_user_hidden_entities_remain_hidden(hass: HomeAssistant) -> None:
    entity_reg = er.async_get(hass)
    entity_reg.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        "abcdef",
        suggested_object_id="test_power",
        hidden_by=er.RegistryEntryHider.USER,
    )
    await hass.async_block_till_done()

    await run_powercalc_setup(
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

    assert (
        entity_reg.async_get("sensor.test_power").hidden_by
        is er.RegistryEntryHider.USER
    )


async def test_members_are_unhiden_after_group_removed(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
) -> None:
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "abcdef",
        suggested_object_id="test_power",
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


async def test_group_utility_meter(
    hass: HomeAssistant, entity_reg: EntityRegistry
) -> None:
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "abcdef",
        suggested_object_id="testgroup_power",
    )
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "abcdef_energy",
        suggested_object_id="testgroup_energy",
    )

    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup(
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


async def test_include_config_entries_in_group(hass: HomeAssistant) -> None:
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
        "sensor.virtualsensor_energy",
    }


async def test_add_virtual_power_sensor_to_group_on_creation(
    hass: HomeAssistant,
) -> None:
    """
    When creating a virtual power sensor using the config flow you can define a group you want to add it to
    Test that the new sensors are added to the existing group correctly
    """

    config_entry_sensor1 = await create_mocked_virtual_power_sensor_entry(
        hass,
        "VirtualSensor1",
        "xyz",
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
        config_entry_group.entry_id,
    )
    assert config_entry_sensor1.entry_id in config_entry_group.data.get(
        CONF_GROUP_MEMBER_SENSORS,
    )
    assert config_entry_sensor2.entry_id in config_entry_group.data.get(
        CONF_GROUP_MEMBER_SENSORS,
    )

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
        config_entry_group.entry_id,
    )
    assert config_entry_group.data.get(CONF_GROUP_MEMBER_SENSORS) == [
        config_entry_sensor1.entry_id,
    ]

    group_state = hass.states.get("sensor.groupa_power")
    assert group_state
    assert group_state.attributes.get("entities") == {
        "sensor.virtualsensor1_power",
    }


async def test_virtual_power_sensor_is_not_added_twice_to_group_after_reload(
    hass: HomeAssistant,
) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/1298"""

    config_entry_group = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
        },
    )
    config_entry_group.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_group.entry_id)
    await hass.async_block_till_done()

    config_entry_sensor = MockConfigEntry(
        domain=DOMAIN,
        unique_id="xyz",
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "xyz",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_GROUP: config_entry_group.entry_id,
        },
        title="Test",
    )

    config_entry_sensor.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry_group,
        data={
            **config_entry_group.data,
            CONF_GROUP_MEMBER_SENSORS: [config_entry_sensor.entry_id],
        },
    )
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(config_entry_sensor.entry_id)

    # Trigger a reload
    assert await hass.config_entries.async_reload(config_entry_sensor.entry_id)
    await hass.async_block_till_done()

    config_entry_group = hass.config_entries.async_get_entry(
        config_entry_group.entry_id,
    )
    assert config_entry_group.data.get(CONF_GROUP_MEMBER_SENSORS) == [
        config_entry_sensor.entry_id,
    ]


async def test_custom_naming_pattern(hass: HomeAssistant) -> None:
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup(
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


async def test_disable_extended_attributes(hass: HomeAssistant) -> None:
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1", 50),
                get_simple_fixed_config("input_boolean.test2", 50),
            ],
        },
        {CONF_DISABLE_EXTENDED_ATTRIBUTES: True},
    )

    power_state = hass.states.get("sensor.testgroup_power")
    assert ATTR_ENTITIES not in power_state.attributes
    assert ATTR_IS_GROUP not in power_state.attributes

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert ATTR_ENTITIES not in energy_state.attributes
    assert ATTR_IS_GROUP not in energy_state.attributes


async def test_config_entry_is_removed_from_associated_groups_on_removal(
    hass: HomeAssistant,
) -> None:
    config_entry_sensor = await create_mocked_virtual_power_sensor_entry(
        hass,
        "VirtualSensor1",
        "xyz",
    )

    groups: list[str] = ["GroupA", "GroupB", "GroupC"]
    group_entry_ids: list[str] = []
    for group in groups:
        config_entry_group = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_SENSOR_TYPE: SensorType.GROUP,
                CONF_NAME: group,
                CONF_GROUP_MEMBER_SENSORS: [config_entry_sensor.entry_id],
            },
        )
        config_entry_group.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry_group.entry_id)
        await hass.async_block_till_done()
        group_entry_ids.append(config_entry_group.entry_id)

    await hass.config_entries.async_remove(config_entry_sensor.entry_id)
    await hass.async_block_till_done()

    for group_entry_id in group_entry_ids:
        group_entry = hass.config_entries.async_get_entry(group_entry_id)
        assert len(group_entry.data.get(CONF_GROUP_MEMBER_SENSORS)) == 0


async def test_group_is_removed_from_virtual_power_entry_on_removal(
    hass: HomeAssistant,
) -> None:
    config_entry_group = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
        },
    )
    config_entry_group.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_group.entry_id)
    await hass.async_block_till_done()

    config_entry_sensor = MockConfigEntry(
        domain=DOMAIN,
        unique_id="xyz",
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "xyz",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_GROUP: config_entry_group.entry_id,
        },
        title="Test",
    )
    config_entry_sensor.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_sensor.entry_id)
    await hass.async_block_till_done()

    # Remove the group from HA
    await hass.config_entries.async_remove(config_entry_group.entry_id)
    await hass.async_block_till_done()

    sensor_entry = hass.config_entries.async_get_entry(config_entry_sensor.entry_id)
    assert sensor_entry.data.get(CONF_GROUP) is None


async def test_error_is_logged_when_config_entry_associated_to_non_existing_group(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_GROUP: "non-existing-config-entry-id",
        },
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert (
        "ConfigEntry Mock Title: Cannot add/remove to group non-existing-config-entry-id. It does not exist"
        in caplog.text
    )


async def test_energy_unit_conversions(hass: HomeAssistant) -> None:
    config_entry_group = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_ENERGY_ENTITIES: [
                "sensor.energy_Wh",
                "sensor.energy_kWh",
                "sensor.energy_MWh",
            ],
        },
    )
    config_entry_group.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_group.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set(
        "sensor.energy_Wh",
        "200",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.energy_kWh",
        "0.1",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.energy_MWh",
        "0.01",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.MEGA_WATT_HOUR},
    )

    await hass.async_block_till_done()

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state.state == "10.3000"


async def test_power_unit_conversions(hass: HomeAssistant) -> None:
    config_entry_group = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_POWER_ENTITIES: ["sensor.power_w", "sensor.power_kw"],
            CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.NONE,
        },
    )
    config_entry_group.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_group.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set(
        "sensor.power_w",
        "100",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT},
    )
    hass.states.async_set(
        "sensor.power_kw",
        "0.1",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT},
    )

    await hass.async_block_till_done()

    energy_state = hass.states.get("sensor.testgroup_power")
    assert energy_state.state == "200.00"


async def test_gui_discovered_entity_in_yaml_group(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Test if a powercalc entity setup with the GUI (either discovered or manually) can be added to a YAML group
    """

    caplog.set_level(logging.ERROR)

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "media_player.mediabox",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "GroupA",
            CONF_ENTITIES: [{CONF_ENTITY_ID: "media_player.mediabox"}],
        },
    )

    assert len(caplog.records) == 0


async def test_ignore_unavailable_state(hass: HomeAssistant) -> None:
    await create_input_booleans(hass, ["test1", "test2"])

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "input_boolean.test1",
                    CONF_STANDBY_POWER: 1.5,
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 20},
                },
                {
                    CONF_ENTITY_ID: "input_boolean.test2",
                    CONF_STANDBY_POWER: 1.5,
                    CONF_MODE: CalculationStrategy.FIXED,
                    CONF_FIXED: {CONF_POWER: 30},
                },
            ],
        },
        {
            CONF_UNAVAILABLE_POWER: 0,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    hass.states.async_set("input_boolean.test1", STATE_UNAVAILABLE)
    hass.states.async_set("input_boolean.test2", STATE_UNAVAILABLE)

    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_power").state == "0.00"


async def test_energy_sensor_delta_updates_new_sensor(hass: HomeAssistant) -> None:
    config_entry_group = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a_energy", "sensor.b_energy"],
        },
    )
    config_entry_group.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_group.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("sensor.a_energy", "2.00")
    hass.states.async_set("sensor.b_energy", "3.00")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_energy").state == "5.0000"

    hass.states.async_set("sensor.a_energy", "2.10")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_energy").state == "5.1000"

    # Simulate a reset, this should just be ignored.
    hass.states.async_set("sensor.a_energy", "0.00")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_energy").state == "5.1000"

    hass.states.async_set("sensor.a_energy", "0.20")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_energy").state == "5.3000"


async def test_energy_sensor_delta_updates_existing_sensor(hass: HomeAssistant) -> None:
    config_entry_group = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a_energy", "sensor.b_energy"],
        },
    )
    config_entry_group.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry_group.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("sensor.testgroup_energy", "5.00")
    await hass.async_block_till_done()

    hass.states.async_set("sensor.a_energy", "2.00")
    hass.states.async_set("sensor.b_energy", "3.00")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_energy").state == "5.0000"

    hass.states.async_set("sensor.a_energy", "2.50")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testgroup_energy").state == "5.5000"


async def test_storage(hass: HomeAssistant) -> None:
    state = State("sensor.dummy_power", "20.00")

    store = PreviousStateStore(hass)
    store.set_entity_state("sensor.dummy", state)
    await store.persist_states()
    await hass.async_block_till_done()

    # Retrieving singleton instance should retrieve and decode persisted states
    store: PreviousStateStore = await PreviousStateStore.async_get_instance(hass)
    store_state = store.get_entity_state("sensor.dummy")

    assert state.entity_id == store_state.entity_id
    assert state.state == store_state.state
    assert state.last_updated == store_state.last_updated
