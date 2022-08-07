from homeassistant.components import input_boolean, light
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import create_domain_groups
from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_FIXED,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    DOMAIN_CONFIG,
    DUMMY_ENTITY_ID,
    SensorType,
)
from custom_components.test.light import MockLight

from .common import (
    create_input_boolean,
    create_mock_light_entity,
    get_simple_fixed_config,
    run_powercalc_setup_yaml_config,
)


async def test_autodiscovery(hass: HomeAssistant):
    """Test that models are automatically discovered and power sensors created"""

    lighta = MockLight("testa")
    lighta.manufacturer = "lidl"
    lighta.model = "HG06106C"

    lightb = MockLight("testb")
    lightb.manufacturer = "signify"
    lightb.model = "LCA001"

    lightc = MockLight("testc")
    lightc.manufacturer = "lidl"
    lightc.model = "NONEXISTING"
    await create_mock_light_entity(hass, [lighta, lightb, lightc])

    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testa_power")
    assert hass.states.get("sensor.testb_power")
    assert not hass.states.get("sensor.testc_power")


async def test_autodiscovery_disabled(hass: HomeAssistant):
    """Test that power sensors are not automatically added when auto discovery is disabled"""

    light_entity = MockLight("testa")
    light_entity.manufacturer = "lidl"
    light_entity.model = "HG06106C"
    await create_mock_light_entity(hass, light_entity)

    await async_setup_component(
        hass, DOMAIN, {DOMAIN: {CONF_ENABLE_AUTODISCOVERY: False}}
    )
    await hass.async_block_till_done()

    assert not hass.states.get("sensor.testa_power")


async def test_domain_groups(hass: HomeAssistant):
    await create_input_boolean(hass)

    domain_config = {
        CONF_ENABLE_AUTODISCOVERY: False,
        CONF_CREATE_DOMAIN_GROUPS: [
            input_boolean.DOMAIN,
            light.DOMAIN,  # No light entities were created, so this group should not be created
        ],
    }

    await run_powercalc_setup_yaml_config(
        hass, get_simple_fixed_config("input_boolean.test", 100), domain_config
    )

    # Triggering start even does not trigger create_domain_groups
    # Need to further investigate this
    # For now just call create_domain_groups manually
    # hass.bus.async_fire(EVENT_HOMEASSISTANT_START)

    await create_domain_groups(
        hass, hass.data[DOMAIN][DOMAIN_CONFIG], [input_boolean.DOMAIN, light.DOMAIN]
    )
    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.all_input_boolean_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.test_power"}

    assert not hass.states.get("sensor.all_light_power")


async def test_unload_entry(hass: HomeAssistant, entity_reg: EntityRegistry):
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

    assert not hass.states.get("sensor.testentry_power")
    assert not entity_reg.async_get("sensor.testentry_power")


async def test_domain_light_group_with_autodiscovery_enabled(hass: HomeAssistant):
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/939
    """
    light_entity = MockLight("testb")
    light_entity.manufacturer = "signify"
    light_entity.model = "LCA001"

    await create_mock_light_entity(hass, light_entity)

    domain_config = {
        CONF_ENABLE_AUTODISCOVERY: True,
        CONF_CREATE_DOMAIN_GROUPS: [light.DOMAIN],
        CONF_CREATE_UTILITY_METERS: True,
        CONF_UTILITY_METER_TYPES: ["daily"],
    }

    await run_powercalc_setup_yaml_config(hass, {}, domain_config)

    await create_domain_groups(hass, hass.data[DOMAIN][DOMAIN_CONFIG], [light.DOMAIN])
    await hass.async_block_till_done()

    assert hass.states.get("sensor.all_light_power")
    assert hass.states.get("sensor.all_light_energy")
    assert not hass.states.get("sensor.all_light_energy_2")
    assert hass.states.get("sensor.all_light_energy_daily")
