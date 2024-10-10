from homeassistant.components import input_boolean, light
from homeassistant.components.utility_meter.const import DAILY
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_STARTED,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import EntityRegistry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import async_migrate_entry, repair_none_config_entries_issue
from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_FIXED,
    CONF_GROUP_MEMBER_SENSORS,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_PLAYBOOK,
    CONF_POWER,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STATE_TRIGGER,
    CONF_STATES_TRIGGER,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    DUMMY_ENTITY_ID,
    ENTRY_DATA_ENERGY_ENTITY,
    ENTRY_DATA_POWER_ENTITY,
    SensorType,
)

from .common import (
    create_input_boolean,
    create_mocked_virtual_power_sensor_entry,
    get_simple_fixed_config,
    run_powercalc_setup,
    setup_config_entry,
)
from .conftest import MockEntityWithModel


async def test_domain_groups(hass: HomeAssistant, entity_reg: EntityRegistry) -> None:
    await create_input_boolean(hass)

    domain_config = {
        CONF_ENABLE_AUTODISCOVERY: False,
        CONF_CREATE_DOMAIN_GROUPS: [
            input_boolean.DOMAIN,
            light.DOMAIN,  # No light entities were created, so this group should not be created
        ],
    }

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("input_boolean.test", 100),
        domain_config,
    )

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.all_input_boolean_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.test_power"}

    assert hass.states.get("sensor.all_light_power").state == STATE_UNAVAILABLE

    entity_entry = entity_reg.async_get("sensor.all_input_boolean_power")
    assert entity_entry
    assert entity_entry.platform == "powercalc"


async def test_unload_entry(hass: HomeAssistant, entity_reg: EntityRegistry) -> None:
    unique_id = "98493943242"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_NAME: "testentry",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_FIXED: {CONF_POWER: 50},
        },
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testentry_power")
    assert entity_reg.async_get("sensor.testentry_power")

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_domain_group_with_utility_meter(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/939
    """
    mock_entity_with_model_information("light.testb", "signify", "LCA001")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCA001",
            CONF_UNIQUE_ID: "1234",
            CONF_ENTITY_ID: "light.testb",
        },
        unique_id="1234",
    )
    entry.add_to_hass(hass)

    domain_config = {
        CONF_ENABLE_AUTODISCOVERY: True,
        CONF_CREATE_DOMAIN_GROUPS: [light.DOMAIN],
        CONF_CREATE_UTILITY_METERS: True,
        CONF_UTILITY_METER_TYPES: [DAILY],
    }

    await run_powercalc_setup(hass, {}, domain_config)

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.all_light_power")
    assert hass.states.get("sensor.all_light_energy")
    assert not hass.states.get("sensor.all_light_energy_2")
    assert hass.states.get("sensor.all_light_energy_daily")


async def test_create_config_entry_without_energy_sensor(
    hass: HomeAssistant,
) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/1544
    """
    template = "{{ 100 * 20 | float}}"

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "testentry",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_FIXED: {CONF_POWER: template, CONF_POWER_TEMPLATE: template},
        },
        unique_id="abcd",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    new_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert new_entry.data == {
        ENTRY_DATA_ENERGY_ENTITY: "sensor.testentry_energy",
        ENTRY_DATA_POWER_ENTITY: "sensor.testentry_power",
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_NAME: "testentry",
        CONF_ENTITY_ID: DUMMY_ENTITY_ID,
        CONF_FIXED: {
            CONF_POWER_TEMPLATE: template,
        },
    }
    assert new_entry.version == 4


async def test_repair_issue_with_none_sensors(hass: HomeAssistant) -> None:
    """
    Test that none named sensors that were created because of a bug are removed on start up.
    See https://github.com/bramstroker/homeassistant-powercalc/issues/2281
    """
    power_entry = await create_mocked_virtual_power_sensor_entry(hass, "Power")

    none_entries = [
        await setup_config_entry(
            hass,
            {
                CONF_SENSOR_TYPE: SensorType.GROUP,
                CONF_NAME: "None",
                CONF_GROUP_MEMBER_SENSORS: [power_entry.entry_id],
            },
            "None",
            "None",
        )
        for _ in range(10)
    ]

    for entry in none_entries:
        assert hass.config_entries.async_get_entry(entry.entry_id)
    assert hass.states.get("sensor.none_power")
    assert hass.states.get("sensor.none_energy")

    await repair_none_config_entries_issue(hass)

    for entry in none_entries:
        assert not hass.config_entries.async_get_entry(entry.entry_id)
    assert not hass.states.get("sensor.none_power")
    assert not hass.states.get("sensor.none_energy")


async def test_migrate_config_entry_version_4(hass: HomeAssistant) -> None:
    """
    Test that a config entry is migrated from version 4 to version 5.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "testentry",
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_PLAYBOOK: {
                CONF_STATES_TRIGGER: {
                    "foo": "bar",
                },
            },
        },
        version=3,
    )
    entry.add_to_hass(hass)

    await async_migrate_entry(hass, entry)

    assert entry.version == 4
    assert entry.data == {
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_NAME: "testentry",
        CONF_ENTITY_ID: DUMMY_ENTITY_ID,
        CONF_PLAYBOOK: {
            CONF_STATE_TRIGGER: {
                "foo": "bar",
            },
        },
    }
