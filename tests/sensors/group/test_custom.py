from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
import logging
from typing import Any
from unittest.mock import patch

from freezegun import freeze_time
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.utility_meter.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_DEVICE,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util import dt
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    RegistryEntryWithDefaults,
    async_fire_time_changed,
    mock_device_registry,
    mock_registry,
    mock_restore_cache_with_extra_data,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_IS_GROUP,
    ATTR_MEMBERS,
    ATTR_STATE,
    CONF_AREA,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_FORCE_CALCULATE_GROUP_ENERGY,
    CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED,
    CONF_GROUP,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_ENERGY_START_AT_ZERO,
    CONF_GROUP_ENERGY_UPDATE_INTERVAL,
    CONF_GROUP_MEMBER_DEVICES,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_GROUP_POWER_ENTITIES,
    CONF_GROUP_POWER_UPDATE_INTERVAL,
    CONF_GROUP_TYPE,
    CONF_HIDE_MEMBERS,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_POWER,
    CONF_SUB_GROUPS,
    CONF_UNAVAILABLE_POWER,
    DATA_GROUP_ENTITIES,
    DEFAULT_ENERGY_UPDATE_INTERVAL,
    DOMAIN,
    DUMMY_ENTITY_ID,
    ENTRY_DATA_ENERGY_ENTITY,
    SERVICE_CALIBRATE_ENERGY,
    SERVICE_DEBUG_GROUP,
    SERVICE_GET_GROUP_ENTITIES,
    SERVICE_RESET_ENERGY,
    CalculationStrategy,
    GroupType,
    SensorType,
    UnitPrefix,
)
from custom_components.powercalc.sensors.group.custom import PreviousStateStore, resolve_entity_ids_recursively
from tests.common import (
    assert_entity_state,
    create_input_booleans,
    create_mock_config_entry,
    create_mocked_virtual_power_sensor_entry,
    get_simple_fixed_config,
    run_powercalc_setup,
    set_states,
)


async def test_grouped_power_sensor(hass: HomeAssistant, entity_registry: EntityRegistry) -> None:
    await set_states(hass, [("input_boolean.test1", STATE_ON), ("input_boolean.test2", STATE_ON)])
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
                    CONF_IGNORE_UNAVAILABLE_STATE: True,
                },
                get_simple_fixed_config("input_boolean.test2", 50),
            ],
        },
    )

    power_state = hass.states.get("sensor.test1_power")
    assert power_state

    power_entry = entity_registry.async_get("sensor.testgroup_power")
    assert power_entry
    assert power_entry.unique_id == "group_unique_id"

    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state
    assert power_state.attributes.get("state_class") == SensorStateClass.MEASUREMENT
    assert power_state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.POWER
    assert power_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfPower.WATT
    assert power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_power",
        "sensor.test2_power",
    }
    assert power_state.state == "60.50"

    await set_states(hass, [("sensor.test1_energy", "40.00")])
    energy_entry = entity_registry.async_get("sensor.testgroup_energy")
    assert energy_entry
    assert energy_entry.unique_id == "group_unique_id_energy"

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state
    assert energy_state.attributes.get("state_class") == SensorStateClass.TOTAL
    assert energy_state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY
    assert energy_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfEnergy.KILO_WATT_HOUR
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_energy",
        "sensor.test2_energy",
    }

    await set_states(hass, [("input_boolean.test1", STATE_OFF)], block_count=0)

    assert_entity_state(hass, "sensor.test1_power", "10.50")


async def test_subgroups_from_config_entry(hass: HomeAssistant) -> None:
    config_entry_group_a = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test1_power"],
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.test1_energy"],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    config_entry_group_b = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupB",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test2_power"],
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.test2_energy"],
            CONF_SUB_GROUPS: [
                config_entry_group_a.entry_id,
                "464354354543",  # Non existing entry_id, should not break setup
            ],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupC",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test3_power"],
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.test3_energy"],
            CONF_SUB_GROUPS: [config_entry_group_b.entry_id],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

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


async def test_parent_group_reloaded_on_subgroup_update(hass: HomeAssistant) -> None:
    """When an entity is added to a subgroup all the groups referring this subgroup should be reloaded"""

    config_entry_group_sub = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupSub",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test1_power"],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupMain",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test2_power"],
            CONF_SUB_GROUPS: [
                config_entry_group_sub.entry_id,
            ],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    main_group_state = hass.states.get("sensor.groupmain_power")
    assert main_group_state
    assert main_group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test1_power",
        "sensor.test2_power",
    }

    hass.config_entries.async_update_entry(
        config_entry_group_sub,
        data={
            **config_entry_group_sub.data,
            CONF_GROUP_POWER_ENTITIES: ["sensor.test1_power", "sensor.test3_power"],
        },
    )

    main_group_state = hass.states.get("sensor.groupmain_power")
    assert main_group_state
    assert main_group_state.attributes.get(ATTR_ENTITIES) == {
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
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1"),
                get_simple_fixed_config("input_boolean.test2"),
            ],
        },
    )

    # Set the individual entities to some initial values
    await set_states(
        hass,
        [
            (
                "sensor.test1_energy",
                "0.8",
                {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
            ),
            (
                "sensor.test2_energy",
                "1.2",
                {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
            ),
        ],
    )
    assert_entity_state(hass, "sensor.testgroup_energy", "2.0000")

    # Reset the group sensor and underlying group members
    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=60),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RESET_ENERGY,
            {
                ATTR_ENTITY_ID: "sensor.testgroup_energy",
            },
            blocking=True,
        )

    assert_entity_state(hass, "sensor.testgroup_energy", "0.0000")
    assert_entity_state(hass, "sensor.test1_energy", "0.0000")
    assert_entity_state(hass, "sensor.test2_energy", "0.0000")

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=120),
    ):
        await set_states(
            hass,
            [
                (
                    "sensor.test2_energy",
                    "0.5",
                    {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
                ),
            ],
        )
    assert_entity_state(hass, "sensor.testgroup_energy", "0.5000")


async def test_calibrate_service(hass: HomeAssistant) -> None:
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

    await set_states(hass, [("sensor.test1_energy", "20")])
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CALIBRATE_ENERGY,
        {
            ATTR_ENTITY_ID: "sensor.testgroup_energy",
            "value": "100",
        },
        blocking=True,
    )

    assert_entity_state(hass, "sensor.testgroup_energy", "100.0000")


@pytest.mark.parametrize(
    "last_state,last_sensor_data,expected_state,expect_warning",
    [
        (
            State("sensor.testgroup_energy", "0.5000"),
            {"native_unit_of_measurement": None, "native_value": 0.5},
            "0.5000",
            False,
        ),
        (
            State("sensor.testgroup_energy", STATE_UNAVAILABLE),
            {"native_unit_of_measurement": None, "native_value": None},
            "0.0000",
            False,
        ),
        (
            State("sensor.testgroup_energy", "boo"),
            {"native_unit_of_measurement": None, "native_value": None},
            "0.0000",
            True,
        ),
    ],
)
async def test_restore_state(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    last_state: State,
    last_sensor_data: Mapping[str, Any],
    expected_state: str,
    expect_warning: bool,
) -> None:
    caplog.set_level(logging.WARNING)
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                last_state,
                last_sensor_data,
            ),
        ),
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                get_simple_fixed_config("switch.test"),
            ],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    if expect_warning:
        assert "Could not restore last state" in caplog.text

    assert_entity_state(hass, "sensor.testgroup_energy", expected_state)


async def test_mega_watt_hour(hass: HomeAssistant) -> None:
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
    await set_states(hass, [("input_boolean.test1", STATE_UNAVAILABLE), ("input_boolean.test2", STATE_UNAVAILABLE)])
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

    assert_entity_state(hass, "sensor.testgroup_power", STATE_UNAVAILABLE)
    assert_entity_state(hass, "sensor.testgroup_energy", STATE_UNAVAILABLE)

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=60),
    ):
        await set_states(hass, [("input_boolean.test1", STATE_ON)], block_count=3)
        power_state = hass.states.get("sensor.testgroup_power")
        assert power_state.state != STATE_UNAVAILABLE

        assert_entity_state(hass, "sensor.testgroup_energy", STATE_UNAVAILABLE)


async def test_energy_group_available_when_members_temporarily_unavailable(
    hass: HomeAssistant,
) -> None:
    """
    When any of the member sensors of a grouped energy sensor become unavailable,
     we try to use the last know correct state value of the member sensor
    """
    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1", 50),
                get_simple_fixed_config("input_boolean.test2", 50),
            ],
        },
    )

    await set_states(hass, [("sensor.test1_energy", "1.0"), ("sensor.test2_energy", "2.0")])
    assert_entity_state(hass, "sensor.testgroup_energy", "3.0000")

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=60),
    ):
        await set_states(hass, [("sensor.test1_energy", STATE_UNAVAILABLE)])
        assert_entity_state(hass, "sensor.testgroup_energy", "3.0000")

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=120),
    ):
        await set_states(hass, [("sensor.test2_energy", "2.2")])
        assert_entity_state(hass, "sensor.testgroup_energy", "3.2000")


async def test_hide_members(hass: HomeAssistant, entity_registry: EntityRegistry) -> None:
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

    assert entity_registry.async_get("sensor.one_power").hidden_by == er.RegistryEntryHider.INTEGRATION
    assert entity_registry.async_get("sensor.two_power").hidden_by == er.RegistryEntryHider.INTEGRATION


async def test_unhide_members(hass: HomeAssistant, entity_registry: EntityRegistry) -> None:
    entity_registry.async_get_or_create(
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

    assert entity_registry.async_get("sensor.test_power").hidden_by is None


async def test_user_hidden_entities_remain_hidden(hass: HomeAssistant, entity_registry: EntityRegistry) -> None:
    entity_registry.async_get_or_create(
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

    assert entity_registry.async_get("sensor.test_power").hidden_by is er.RegistryEntryHider.USER


async def test_members_are_unhiden_after_group_removed(
    hass: HomeAssistant,
    entity_registry: EntityRegistry,
) -> None:
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "abcdef",
        suggested_object_id="test_power",
    )

    config_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "MyGroup",
            CONF_GROUP_POWER_ENTITIES: ["sensor.test_power"],
            CONF_HIDE_MEMBERS: True,
        },
    )

    assert hass.states.get("sensor.mygroup_power")
    assert entity_registry.async_get("sensor.test_power").hidden_by == er.RegistryEntryHider.INTEGRATION

    # Remove the config entry
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get("sensor.test_power").hidden_by is None

    assert not hass.states.get("sensor.mygroup_power")
    assert not entity_registry.async_get("sensor.mygroup_power")


async def test_group_utility_meter(
    hass: HomeAssistant,
    entity_registry: EntityRegistry,
) -> None:
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "abcdef",
        suggested_object_id="testgroup_power",
    )
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "abcdef_energy",
        suggested_object_id="testgroup_energy",
    )

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


async def test_include_config_entries_in_group(hass: HomeAssistant) -> None:
    config_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UNIQUE_ID: "abcdef",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "VirtualSensor",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
            CONF_GROUP_MEMBER_SENSORS: [config_entry.entry_id],
            CONF_GROUP_POWER_ENTITIES: ["sensor.other_power"],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

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

    config_entry_group = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
            CONF_GROUP_MEMBER_SENSORS: [config_entry_sensor1.entry_id],
        },
    )

    config_entry_sensor2 = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "VirtualSensor2",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_UNIQUE_ID: "abc",
            CONF_GROUP: config_entry_group.entry_id,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

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

    config_entry_group = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
        },
    )

    config_entry_sensor = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "xyz",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_GROUP: config_entry_group.entry_id,
        },
        setup=False,
    )

    hass.config_entries.async_update_entry(
        config_entry_group,
        data={
            **config_entry_group.data,
            CONF_GROUP_MEMBER_SENSORS: [config_entry_sensor.entry_id],
        },
    )
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


async def test_associate_entry_to_existing_group(hass: HomeAssistant) -> None:
    config_entry_group = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "MyGroup",
        },
    )
    config_entry_sensor = await create_mocked_virtual_power_sensor_entry(hass, "MySensor", extra_config={CONF_GROUP: config_entry_group.entry_id})

    assert config_entry_group.data.get(CONF_GROUP_MEMBER_SENSORS) == [config_entry_sensor.entry_id]
    assert CONF_GROUP not in config_entry_sensor.data


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
        config_entry_group = await create_mock_config_entry(
            hass,
            {
                CONF_SENSOR_TYPE: SensorType.GROUP,
                CONF_NAME: group,
                CONF_GROUP_MEMBER_SENSORS: [config_entry_sensor.entry_id],
            },
        )
        group_entry_ids.append(config_entry_group.entry_id)

    await hass.config_entries.async_remove(config_entry_sensor.entry_id)
    await hass.async_block_till_done()

    for group_entry_id in group_entry_ids:
        group_entry = hass.config_entries.async_get_entry(group_entry_id)
        assert len(group_entry.data.get(CONF_GROUP_MEMBER_SENSORS)) == 0


async def test_group_is_removed_from_virtual_power_entry_on_removal(
    hass: HomeAssistant,
) -> None:
    config_entry_group = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "GroupA",
        },
    )

    config_entry_sensor = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "xyz",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_GROUP: config_entry_group.entry_id,
        },
    )

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
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_GROUP: "1l3b47ropjnksgkd1rh30e8opvqwnngt",
        },
    )

    assert "ConfigEntry Mock Title: Cannot add/remove to group 1l3b47ropjnksgkd1rh30e8opvqwnngt. It does not exist" in caplog.text


async def test_energy_unit_conversions(hass: HomeAssistant) -> None:
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_NAME: "TestGroup",
            CONF_GROUP_ENERGY_ENTITIES: [
                "sensor.energy_Wh",
                "sensor.energy_kWh",
                "sensor.energy_MWh",
            ],
        },
    )

    await set_states(
        hass,
        [
            (
                "sensor.energy_Wh",
                "200",
                {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.WATT_HOUR},
            ),
            (
                "sensor.energy_kWh",
                "0.1",
                {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
            ),
            (
                "sensor.energy_MWh",
                "0.01",
                {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.MEGA_WATT_HOUR},
            ),
        ],
    )
    assert_entity_state(hass, "sensor.testgroup_energy", "10.3000")


async def test_power_unit_conversions(hass: HomeAssistant) -> None:
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_POWER_ENTITIES: ["sensor.power_w", "sensor.power_kw"],
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.energy_w", "sensor.energy_kw"],
            CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.NONE,
        },
    )

    await set_states(
        hass,
        [
            (
                "sensor.power_w",
                "100",
                {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT},
            ),
            (
                "sensor.power_kw",
                "0.1",
                {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT},
            ),
        ],
    )
    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state
    assert power_state.state == "200.00"
    assert power_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfPower.WATT

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfEnergy.WATT_HOUR


async def test_gui_discovered_entity_in_yaml_group(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Test if a powercalc entity setup with the GUI (either discovered or manually) can be added to a YAML group
    """

    caplog.set_level(logging.ERROR)

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "media_player.mediabox",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "GroupA",
            CONF_ENTITIES: [{CONF_ENTITY_ID: "media_player.mediabox"}],
        },
    )

    assert len(caplog.records) == 0


async def test_ignore_unavailable_state(hass: HomeAssistant) -> None:
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

    await set_states(hass, [("input_boolean.test1", STATE_UNAVAILABLE), ("input_boolean.test2", STATE_UNAVAILABLE)])
    assert_entity_state(hass, "sensor.testgroup_power", "0.00")


async def test_energy_sensor_delta_updates_new_sensor(hass: HomeAssistant) -> None:
    await set_states(hass, [("sensor.a_energy", "2.00"), ("sensor.b_energy", "3.00")])
    await _create_energy_group(
        hass,
        "TestGroup",
        ["sensor.a_energy", "sensor.b_energy"],
    )

    assert_entity_state(hass, "sensor.testgroup_energy", "5.0000")

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=60),
    ):
        await set_states(hass, [("sensor.a_energy", "2.10")])
        assert_entity_state(hass, "sensor.testgroup_energy", "5.1000")

    # Simulate a reset, this should just be ignored.
    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=120),
    ):
        await set_states(hass, [("sensor.a_energy", "0.00")])
        assert_entity_state(hass, "sensor.testgroup_energy", "5.1000")

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=180),
    ):
        await set_states(hass, [("sensor.a_energy", "0.20")])
        assert_entity_state(hass, "sensor.testgroup_energy", "5.3000")


async def test_delta_calculation_precision(hass: HomeAssistant) -> None:
    """
    Make sure delta calculation is done on exact decimal value, not the rounded value.
    See: https://github.com/bramstroker/homeassistant-powercalc/issues/2254
    """
    await _create_energy_group(
        hass,
        "TestGroup",
        ["sensor.a_energy"],
    )

    test_values = [
        ("1197.865543", "1197.8655"),
        ("1197.868021", "1197.8680"),
        ("1197.868628", "1197.8686"),
        ("1197.871022", "1197.8710"),
        ("1197.871629", "1197.8716"),
        ("1197.873903", "1197.8739"),
        ("1197.874396", "1197.8744"),
        ("1197.876372", "1197.8764"),
        ("1197.876868", "1197.8769"),
        ("1197.878879", "1197.8789"),
        ("1197.879332", "1197.8793"),
    ]

    for energy_state, expected_group_state in test_values:
        await set_states(hass, [("sensor.a_energy", energy_state, {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})])
        assert_entity_state(hass, "sensor.testgroup_energy", expected_group_state)


async def test_energy_sensor_delta_updates_existing_sensor(hass: HomeAssistant) -> None:
    await _create_energy_group(
        hass,
        "TestGroup",
        ["sensor.a_energy", "sensor.b_energy"],
    )

    await set_states(hass, [("sensor.testgroup_energy", "5.00"), ("sensor.a_energy", "2.00"), ("sensor.b_energy", "3.00")])
    assert_entity_state(hass, "sensor.testgroup_energy", "5.0000")

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=60),
    ):
        await set_states(hass, [("sensor.a_energy", "2.50")])
        assert_entity_state(hass, "sensor.testgroup_energy", "5.5000")


async def test_energy_sensor_in_multiple_groups_calculates_correctly(
    hass: HomeAssistant,
) -> None:
    """
    Test that group energy sensor is calculated correctly when an energy sensor is part of multiple groups
    Fixes https://github.com/bramstroker/homeassistant-powercalc/issues/1673
    """
    await _create_energy_group(
        hass,
        "TestGroupA",
        ["sensor.a_energy", "sensor.b_energy"],
    )
    await _create_energy_group(
        hass,
        "TestGroupB",
        ["sensor.a_energy", "sensor.c_energy"],
    )
    await _create_energy_group(
        hass,
        "TestGroupC",
        ["sensor.a_energy", "sensor.d_energy"],
    )

    await set_states(hass, [("sensor.a_energy", "2.00"), ("sensor.b_energy", "3.00")])
    assert_entity_state(hass, "sensor.testgroupa_energy", "5.0000")
    assert_entity_state(hass, "sensor.testgroupb_energy", "2.0000")
    assert_entity_state(hass, "sensor.testgroupc_energy", "2.0000")

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=60),
    ):
        await set_states(hass, [("sensor.a_energy", "3.21")])
        assert_entity_state(hass, "sensor.testgroupa_energy", "6.2100")
        assert_entity_state(hass, "sensor.testgroupb_energy", "3.2100")
        assert_entity_state(hass, "sensor.testgroupc_energy", "3.2100")


async def test_storage(hass: HomeAssistant) -> None:
    state = State("sensor.dummy_power", "20.00")

    store = PreviousStateStore(hass)
    store.async_setup_dump()
    store.set_entity_state("sensor.group1_energy", "sensor.dummy", state)
    async_fire_time_changed(
        hass,
        dt.utcnow() + timedelta(hours=1),
    )

    await hass.async_block_till_done()

    # Retrieving singleton instance should retrieve and decode persisted states
    store: PreviousStateStore = await PreviousStateStore.async_get_instance(hass)
    store_state = store.get_entity_state("sensor.group1_energy", "sensor.dummy")

    assert state.entity_id == store_state.entity_id
    assert state.state == store_state.state
    assert state.last_updated == store_state.last_updated


async def test_storage_version_1(hass: HomeAssistant) -> None:
    store = PreviousStateStore(hass)
    storage_data = {
        "sensor.dummy": State("sensor.dummy_power", "20.00"),
    }
    store.store.version = 1
    await store.store.async_save(storage_data)
    await hass.async_block_till_done()

    # Retrieving singleton instance should retrieve and decode persisted states
    store: PreviousStateStore = await PreviousStateStore.async_get_instance(hass)
    store_state = store.get_entity_state("sensor.group1_energy", "sensor.dummy")

    assert store_state is None


async def test_unknown_member_config_entry_is_skipped_from_group(
    hass: HomeAssistant,
) -> None:
    member_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "group",
            CONF_GROUP_MEMBER_SENSORS: [member_entry.entry_id, "foobar"],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    assert hass.states.get("sensor.group_power").attributes.get("entities") == {
        "sensor.test_power",
    }


async def test_reference_existing_sensor_in_group(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        [
            get_simple_fixed_config("switch.test"),
            {
                CONF_CREATE_GROUP: "TestGroup",
                CONF_ENTITIES: [
                    {
                        CONF_ENTITY_ID: "switch.test",
                    },
                ],
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    group_state = hass.states.get("sensor.testgroup_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.test_power"}


async def test_create_group_with_real_power_sensors(hass: HomeAssistant) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/1895"""

    mock_registry(
        hass,
        {
            "sensor.existing_power": RegistryEntryWithDefaults(
                entity_id="sensor.existing_power",
                unique_id="1234",
                platform="sensor",
                device_id="shelly-device-id",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.existing_energy": RegistryEntryWithDefaults(
                entity_id="sensor.existing_energy",
                unique_id="12345",
                platform="sensor",
                device_id="shelly-device-id",
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "TestGroup",
                CONF_ENTITIES: [
                    {
                        CONF_POWER_SENSOR_ID: "sensor.existing_power",
                        CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
                    },
                ],
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    group_state = hass.states.get("sensor.testgroup_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.existing_power"}


async def test_bind_to_configured_device(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: DeviceRegistry,
) -> None:
    """
    Test that all powercalc created sensors are attached to same device as the source entity
    """

    # Create a device
    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={("dummy", "abcdef")},
        manufacturer="Google Inc.",
        model="Google Home Mini",
    )

    # Create powercalc sensors
    member_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "MyGroup",
            CONF_DEVICE: device_entry.id,
            CONF_GROUP_MEMBER_SENSORS: [member_entry.entry_id],
        },
    )

    # Assert that all the entities are bound to correct device
    group_entity = entity_registry.async_get("sensor.mygroup_power")
    assert group_entity
    assert group_entity.device_id == device_entry.id


async def test_disable_energy_sensor_creation(hass: HomeAssistant) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/2143"""
    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                get_simple_fixed_config("input_boolean.test1"),
                get_simple_fixed_config("input_boolean.test2"),
            ],
            CONF_CREATE_ENERGY_SENSOR: False,
        },
    )

    assert hass.states.get("sensor.testgroup_energy") is None


async def test_disable_energy_sensor_creation_gui(hass: HomeAssistant) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/2143"""
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_CREATE_ENERGY_SENSOR: False,
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a_energy", "sensor.b_energy"],
        },
    )

    assert hass.states.get("sensor.testgroup_energy") is None


async def test_inital_group_sum_calculated(hass: HomeAssistant) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/1922"""
    await set_states(hass, [("sensor.my_power", STATE_UNAVAILABLE)])
    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "TestGroup",
                CONF_IGNORE_UNAVAILABLE_STATE: True,
                CONF_ENTITIES: [
                    {
                        CONF_POWER_SENSOR_ID: "sensor.my_power",
                    },
                ],
            },
        ],
    )

    assert_entity_state(hass, "sensor.testgroup_power", "0.00")


async def test_additional_energy_sensors(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "sensor.furnace_power": RegistryEntryWithDefaults(
                entity_id="sensor.furnace_power",
                unique_id="1111",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.furnace_energy": RegistryEntryWithDefaults(
                entity_id="sensor.furnace_energy",
                unique_id="2222",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "TestGroup",
                CONF_IGNORE_UNAVAILABLE_STATE: True,
                CONF_CREATE_ENERGY_SENSOR: True,
                CONF_ENTITIES: [
                    {
                        CONF_ENTITY_ID: "fan.ceiling_fan",
                        CONF_FIXED: {CONF_POWER: 50},
                        CONF_CREATE_ENERGY_SENSOR: True,
                    },
                    {
                        CONF_POWER_SENSOR_ID: "sensor.furnace_power",
                        CONF_ENERGY_SENSOR_ID: "sensor.furnace_energy",
                    },
                ],
            },
        ],
        {
            CONF_CREATE_ENERGY_SENSORS: False,
        },
    )

    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state.attributes.get(ATTR_ENTITIES) == {"sensor.ceiling_fan_power", "sensor.furnace_power"}

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state.attributes.get(ATTR_ENTITIES) == {"sensor.ceiling_fan_energy", "sensor.furnace_energy"}


async def test_force_calculate_energy_sensor(hass: HomeAssistant) -> None:
    """
    When `force_calculate_group_energy` is set to true,
    the energy sensor should be a Riemann sensor integrating the power sensor
    """

    mock_registry(
        hass,
        {
            "sensor.furnace_power": RegistryEntryWithDefaults(
                entity_id="sensor.furnace_power",
                unique_id="1111",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.lights_power": RegistryEntryWithDefaults(
                entity_id="sensor.lights_power",
                unique_id="2222",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "TestGroup",
                CONF_IGNORE_UNAVAILABLE_STATE: True,
                CONF_CREATE_ENERGY_SENSOR: True,
                CONF_FORCE_CALCULATE_GROUP_ENERGY: True,
                CONF_ENTITIES: [
                    {
                        CONF_POWER_SENSOR_ID: "sensor.furnace_power",
                    },
                    {
                        CONF_POWER_SENSOR_ID: "sensor.lights_power",
                    },
                ],
            },
        ],
        {
            CONF_CREATE_ENERGY_SENSORS: False,
            CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED: 60,
            CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.KILO,
        },
    )

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state
    assert energy_state.attributes.get(ATTR_DEVICE_CLASS) == SensorDeviceClass.ENERGY
    assert energy_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfEnergy.KILO_WATT_HOUR


async def test_decimal_conversion_error_is_logged(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "TestGroup",
                CONF_IGNORE_UNAVAILABLE_STATE: True,
                CONF_ENTITIES: [
                    {
                        CONF_POWER_SENSOR_ID: "sensor.test",
                    },
                ],
            },
        ],
    )
    await set_states(hass, [("sensor.test", "invalid")])
    assert "Error converting state value" in caplog.text
    assert_entity_state(hass, "sensor.testgroup_power", "0.00")


async def test_force_calculate_energy(hass: HomeAssistant) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/2476
    Test force_calculation_group_energy toggle in config flow applied correctly
    """
    member_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "media_player.mediabox",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_CREATE_ENERGY_SENSOR: True,
        },
    )

    group_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_MEMBER_SENSORS: [member_entry.entry_id],
            CONF_FORCE_CALCULATE_GROUP_ENERGY: True,
        },
    )

    hass.config_entries.async_update_entry(member_entry, data={**member_entry.data, CONF_CREATE_ENERGY_SENSOR: False})
    await hass.config_entries.async_reload(group_entry.entry_id)

    group_state = hass.states.get("sensor.testgroup_energy")
    assert group_state.state is not STATE_UNAVAILABLE


async def test_energy_entity_attribute_is_unset_correctly(hass: HomeAssistant) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/2476
    When `create_energy_sensor` is set to false the `_energy_entity` property in config entry must also be unset.
    """
    member_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "1234",
            CONF_ENTITY_ID: "media_player.mediabox",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_CREATE_ENERGY_SENSOR: True,
        },
        unique_id="1234",
    )

    hass.config_entries.async_update_entry(member_entry, data={**member_entry.data, CONF_CREATE_ENERGY_SENSOR: False})

    member_entry = hass.config_entries.async_get_entry(member_entry.entry_id)
    assert ENTRY_DATA_ENERGY_ENTITY not in member_entry.data


async def test_get_group_entities_action(hass: HomeAssistant) -> None:
    """
    Test that the get_group_entities action returns the correct entities
    """
    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "TestGroup",
                CONF_IGNORE_UNAVAILABLE_STATE: True,
                CONF_ENTITIES: [
                    {
                        CONF_ENTITY_ID: "switch.test1",
                        CONF_FIXED: {CONF_POWER: 50},
                    },
                    {
                        CONF_ENTITY_ID: "switch.test2",
                        CONF_FIXED: {CONF_POWER: 50},
                    },
                    {
                        CONF_ENTITY_ID: "switch.test3",
                        CONF_FIXED: {CONF_POWER: 50},
                    },
                ],
            },
        ],
    )
    await hass.async_block_till_done()

    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_GROUP_ENTITIES,
        {
            ATTR_ENTITY_ID: "sensor.testgroup_energy",
        },
        blocking=True,
        return_response=True,
    )
    assert res["sensor.testgroup_energy"][ATTR_ENTITIES] == {"sensor.test1_energy", "sensor.test2_energy", "sensor.test3_energy"}


async def test_debug_group_action_for_power_group(hass: HomeAssistant) -> None:
    await set_states(
        hass,
        [
            ("sensor.a_power", "50", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}),
            ("sensor.b_power", "0.1", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT}),
        ],
    )
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_POWER_ENTITIES: ["sensor.a_power", "sensor.b_power"],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )
    await hass.async_block_till_done()

    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_DEBUG_GROUP,
        {
            ATTR_ENTITY_ID: "sensor.testgroup_power",
        },
        blocking=True,
        return_response=True,
    )

    assert res["sensor.testgroup_power"] == {
        ATTR_STATE: "150.00",
        ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
        ATTR_MEMBERS: {
            "sensor.a_power": {
                ATTR_STATE: "50.00",
                ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            },
            "sensor.b_power": {
                ATTR_STATE: "100.00",
                ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            },
        },
    }


async def test_debug_group_action_for_power_group_with_unavailable_member(hass: HomeAssistant) -> None:
    await set_states(
        hass,
        [
            ("sensor.a_power", "50", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}),
            ("sensor.b_power", STATE_UNAVAILABLE, {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}),
        ],
    )
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_POWER_ENTITIES: ["sensor.a_power", "sensor.b_power"],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )
    await hass.async_block_till_done()

    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_DEBUG_GROUP,
        {
            ATTR_ENTITY_ID: "sensor.testgroup_power",
        },
        blocking=True,
        return_response=True,
    )

    assert res["sensor.testgroup_power"] == {
        ATTR_STATE: "50.00",
        ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
        ATTR_MEMBERS: {
            "sensor.a_power": {
                ATTR_STATE: "50.00",
                ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            },
            "sensor.b_power": {
                ATTR_STATE: STATE_UNAVAILABLE,
                ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            },
        },
    }


async def test_debug_group_action_for_power_group_with_missing_member_state(hass: HomeAssistant) -> None:
    await set_states(hass, [("sensor.a_power", "50", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT})])
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_POWER_ENTITIES: ["sensor.a_power", "sensor.b_power"],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )
    await hass.async_block_till_done()

    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_DEBUG_GROUP,
        {
            ATTR_ENTITY_ID: "sensor.testgroup_power",
        },
        blocking=True,
        return_response=True,
    )

    assert res["sensor.testgroup_power"] == {
        ATTR_STATE: "50.00",
        ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
        ATTR_MEMBERS: {
            "sensor.a_power": {
                ATTR_STATE: "50.00",
                ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            },
            "sensor.b_power": {
                ATTR_STATE: None,
                ATTR_UNIT_OF_MEASUREMENT: None,
            },
        },
    }


async def test_debug_group_action_for_energy_group(hass: HomeAssistant) -> None:
    await set_states(
        hass,
        [
            ("sensor.a_energy", "2.5", {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR}),
            ("sensor.b_energy", "500", {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.WATT_HOUR}),
        ],
    )
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a_energy", "sensor.b_energy"],
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )
    await hass.async_block_till_done()

    res = await hass.services.async_call(
        DOMAIN,
        SERVICE_DEBUG_GROUP,
        {
            ATTR_ENTITY_ID: "sensor.testgroup_energy",
        },
        blocking=True,
        return_response=True,
    )

    assert res["sensor.testgroup_energy"] == {
        ATTR_STATE: "3.0000",
        ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR,
        ATTR_MEMBERS: {
            "sensor.a_energy": {
                ATTR_STATE: "2.5000",
                ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR,
            },
            "sensor.b_energy": {
                ATTR_STATE: "0.5000",
                ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR,
            },
        },
    }


@pytest.mark.parametrize(
    "entry_data",
    [
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a_energy", "sensor.b_energy"],
            CONF_GROUP_ENERGY_START_AT_ZERO: True,
        },
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a_energy", "sensor.b_energy"],
        },
    ],
)
async def test_start_at_zero(hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
    await set_states(hass, [("sensor.a_energy", "2.00"), ("sensor.b_energy", "3.00")])
    await create_mock_config_entry(hass, entry_data)

    assert_entity_state(hass, "sensor.testgroup_energy", "0.0000")

    with patch(
        "homeassistant.util.utcnow",
        return_value=dt.utcnow() + timedelta(seconds=60),
    ):
        await set_states(hass, [("sensor.a_energy", "2.10")])
        assert_entity_state(hass, "sensor.testgroup_energy", "0.1000")


async def test_energy_throttle(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Test that energy sensor is not updated more than once per minute"""

    def advance(seconds: int) -> None:
        freezer.tick(timedelta(seconds=seconds))
        async_fire_time_changed(hass)

    await set_states(hass, [("sensor.a_energy", "2.00"), ("sensor.b_energy", "3.00")])
    await _create_energy_group(
        hass,
        "TestGroup",
        ["sensor.a_energy", "sensor.b_energy"],
    )

    assert_entity_state(hass, "sensor.testgroup_energy", "5.0000")

    # Do a state change directly after group energy sensor is created
    # These state changes should not be throttled
    await set_states(hass, [("sensor.a_energy", "2.50")])
    assert_entity_state(hass, "sensor.testgroup_energy", "5.5000")

    advance(DEFAULT_ENERGY_UPDATE_INTERVAL + 2)
    # Do 3 state changes after startup period has expired and throttling is activated
    # Only the first state change should be processed and written to state machine
    # Which means 3.50 - 3.00 = 0.50 should be added to the group energy total
    await set_states(hass, [("sensor.b_energy", "3.50"), ("sensor.a_energy", "2.75"), ("sensor.b_energy", "4.00")])
    assert_entity_state(hass, "sensor.testgroup_energy", "6.0000")

    advance(DEFAULT_ENERGY_UPDATE_INTERVAL + 2)
    # Do another state change after the throttle period has expired
    # This state change should be processed and written to state machine, in addition to previously collected state changes
    await set_states(hass, [("sensor.b_energy", "4.25")])
    advance(DEFAULT_ENERGY_UPDATE_INTERVAL + 2)

    assert_entity_state(hass, "sensor.testgroup_energy", "7.0000")


async def test_energy_throttle_disabled(hass: HomeAssistant) -> None:
    """Test that energy sensor throttling can be disabled"""

    await run_powercalc_setup(hass, {}, {CONF_GROUP_ENERGY_UPDATE_INTERVAL: 0})
    await _create_energy_group(
        hass,
        "TestGroup",
        ["sensor.a_energy", "sensor.b_energy"],
    )

    with freeze_time(dt.utcnow() + timedelta(seconds=15)):
        await set_states(
            hass,
            [
                ("sensor.a_energy", "2.00"),
                ("sensor.a_energy", "3.00"),
                ("sensor.a_energy", "4.00"),
                ("sensor.b_energy", "4.00"),
                ("sensor.b_energy", "5.00"),
            ],
        )
        assert_entity_state(hass, "sensor.testgroup_energy", "9.0000")


async def test_power_throttle(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that power sensor updates are throttled."""

    group_entity = "sensor.testgroup_power"
    member1 = "sensor.test_power"
    member2 = "sensor.test2_power"

    def advance(seconds: int) -> None:
        freezer.tick(timedelta(seconds=seconds))
        async_fire_time_changed(hass)

    def get_group_state() -> str:
        return hass.states.get(group_entity).state

    await run_powercalc_setup(
        hass,
        [
            get_simple_fixed_config("switch.test"),
            get_simple_fixed_config("switch.test2"),
            {
                CONF_CREATE_GROUP: "TestGroup",
                CONF_ENTITIES: [
                    {CONF_ENTITY_ID: "switch.test"},
                    {CONF_ENTITY_ID: "switch.test2"},
                ],
                CONF_IGNORE_UNAVAILABLE_STATE: True,
                CONF_CREATE_ENERGY_SENSOR: False,
            },
        ],
        {CONF_GROUP_POWER_UPDATE_INTERVAL: 2},
    )

    group_entity_obj = hass.data[DOMAIN][DATA_GROUP_ENTITIES][group_entity]

    # Set initial member states with a gap so their throttle windows don't overlap.
    await set_states(hass, [(member1, "1.00")])
    advance(5)
    await set_states(hass, [(member2, "1.00")])
    assert get_group_state() == "2.00"

    # ── Window #1: first update passes, second is throttled ─────────────────

    advance(3)

    with patch.object(
        group_entity_obj,
        "async_write_ha_state",
        wraps=group_entity_obj.async_write_ha_state,
    ) as mock_write:
        await set_states(hass, [(member1, "2.00"), (member2, "3.00")])
        # MEMBER_1 → 2.00 triggers an immediate write.
        # MEMBER_2 → 3.00 is throttled; the internal value is updated but a
        # timer is scheduled to flush it later.
        assert mock_write.call_count == 1
        assert get_group_state() == "3.00"  # last flushed value
        assert group_entity_obj._attr_native_value == Decimal("5.00")  # noqa: SLF001

    advance(3)  # fires the scheduled timer → flushes 5.00

    assert get_group_state() == "5.00"

    # ── Window #2: all updates are throttled, timer flushes at end ───────────

    with patch.object(
        group_entity_obj,
        "async_write_ha_state",
        wraps=group_entity_obj.async_write_ha_state,
    ) as mock_write:
        await set_states(hass, [(member2, "6.00"), (member1, "3.00"), (member2, "3.00")])
        # All three updates fall within the throttle window (last write was via
        # the timer), so no immediate write occurs. Internal value reflects the
        # latest sum: MEMBER_1=3 + MEMBER_2=3 = 6.
        assert mock_write.call_count == 0
        assert get_group_state() == "5.00"  # still the old state
        assert group_entity_obj._attr_native_value == Decimal("6.00")  # noqa: SLF001

    advance(3)  # fires the scheduled timer → flushes 6.00

    assert get_group_state() == "6.00"

    # ── Teardown: verify the group returns to 0 after members reset ──────────

    await set_states(hass, [(member1, "0.00"), (member2, "0.00")])
    advance(3)

    assert get_group_state() == "0.00"


async def test_resolve_entity_ids_area(hass: HomeAssistant, area_registry: AreaRegistry) -> None:
    area = area_registry.async_get_or_create("Bedroom")

    mock_registry(
        hass,
        {
            "sensor.test_power": RegistryEntryWithDefaults(
                entity_id="sensor.test_power",
                unique_id=1111,
                platform="powercalc",
                device_class=SensorDeviceClass.POWER,
                area_id=area.id,
            ),
            "sensor.test_energy": RegistryEntryWithDefaults(
                entity_id="sensor.test_energy",
                unique_id=2222,
                platform="powercalc",
                device_class=SensorDeviceClass.ENERGY,
                area_id=area.id,
            ),
        },
    )

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AREA: "Bedroom",
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_GROUP_TYPE: GroupType.CUSTOM,
            CONF_NAME: "TestArea123",
            CONF_SENSOR_TYPE: SensorType.GROUP,
        },
        unique_id="42343887",
    )
    resolved = await resolve_entity_ids_recursively(hass, config_entry, SensorDeviceClass.ENERGY)
    assert resolved == {"sensor.test_energy"}

    resolved = await resolve_entity_ids_recursively(hass, config_entry, SensorDeviceClass.POWER)
    assert resolved == {"sensor.test_power"}


async def test_resolve_entity_ids_skips_tasmota_yesterday_and_today(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "sensor.test_total": RegistryEntryWithDefaults(
                entity_id="sensor.test_total",
                unique_id=1111,
                platform="tasmota",
                device_class=SensorDeviceClass.ENERGY,
                device_id="device_1",
            ),
            "sensor.test_yesterday": RegistryEntryWithDefaults(
                entity_id="sensor.test_yesterday",
                unique_id=2222,
                platform="tasmota",
                device_class=SensorDeviceClass.ENERGY,
                device_id="device_1",
            ),
        },
    )

    mock_device_registry(
        hass,
        {
            "device_1": DeviceEntry(
                id="device_1",
                manufacturer="Tasmota",
                model="Generic",
            ),
        },
    )

    group_entry = MockConfigEntry(
        data={
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_MEMBER_DEVICES: ["device_1"],
            CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        },
    )
    resolved = await resolve_entity_ids_recursively(hass, group_entry, SensorDeviceClass.ENERGY)
    assert resolved == {"sensor.test_total"}


async def test_remove_member_from_group(hass: HomeAssistant) -> None:
    state_storage: PreviousStateStore = await PreviousStateStore.async_get_instance(hass)

    # Setup 3 powercalc virtual power sensor and one group sensor
    member_config_entries = []
    member_entity_ids = []
    for i in range(3):
        config_entry = await create_mock_config_entry(
            hass,
            {
                CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
                CONF_UNIQUE_ID: f"pc{i}",
                CONF_ENTITY_ID: DUMMY_ENTITY_ID,
                CONF_NAME: f"VirtualSensor{i}",
                CONF_MODE: CalculationStrategy.FIXED,
                CONF_FIXED: {CONF_POWER: 50},
            },
        )
        member_config_entries.append(config_entry)
        member_entity_ids.append(f"sensor.virtualsensor{i}_energy")

    group_entry = await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_NAME: "TestGroup",
            CONF_GROUP_MEMBER_SENSORS: [entry.entry_id for entry in member_config_entries],
        },
    )

    # Trigger some changes on member power sensor so the group energy sensor integration logic is executed.
    for i in range(3):
        await set_states(hass, [(f"sensor.virtualsensor{i}_power", "60.00")], block_count=2)

    # Assert the group sensor has the correct 3 member sensors added
    group_state = hass.states.get("sensor.testgroup_energy")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == set(member_entity_ids)

    assert state_storage.get_entity_state("sensor.testgroup_energy", member_entity_ids[0])
    assert state_storage.get_entity_state("sensor.testgroup_energy", member_entity_ids[1])
    assert state_storage.get_entity_state("sensor.testgroup_energy", member_entity_ids[2])

    # Remove one powercalc sensor from the group
    member_config_entries.remove(member_config_entries[1])
    member_entity_ids.remove(member_entity_ids[1])
    hass.config_entries.async_update_entry(
        group_entry,
        data={
            **group_entry.data,
            CONF_GROUP_MEMBER_SENSORS: [entry.entry_id for entry in member_config_entries],
        },
    )

    # Assert the group sensor has the correct 2 member sensors added, and the removed sensor is not there anymore
    group_state = hass.states.get("sensor.testgroup_energy")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == set(member_entity_ids)

    assert state_storage.get_entity_state("sensor.testgroup_energy", member_entity_ids[0])
    assert not state_storage.get_entity_state("sensor.testgroup_energy", "sensor.virtualsensor1_energy")
    assert state_storage.get_entity_state("sensor.testgroup_energy", member_entity_ids[1])


async def _create_energy_group(
    hass: HomeAssistant,
    name: str,
    member_entities: list[str],
) -> None:
    """Create a group energy sensor for testing purposes"""
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_NAME: name,
            CONF_GROUP_ENERGY_ENTITIES: member_entities,
        },
    )
