from homeassistant.core import HomeAssistant, EVENT_HOMEASSISTANT_START
from homeassistant.setup import async_setup_component
from homeassistant.components import input_boolean, light

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_ENABLE_AUTODISCOVERY,
    DOMAIN,
    DOMAIN_CONFIG,
)
from custom_components.test.light import MockLight
from custom_components.powercalc import create_domain_groups

from .common import (
    create_mock_light_entity,
    create_input_boolean,
    get_simple_fixed_config,
    run_powercalc_setup_yaml_config
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
            light.DOMAIN # No light entities were created, so this group should not be created
        ]
    }

    await run_powercalc_setup_yaml_config(
        hass,
        get_simple_fixed_config("input_boolean.test", 100),
        domain_config
    )
    
    # Triggering start even does not trigger create_domain_groups
    # Need to further investigate this
    # For now just call create_domain_groups manually
    #hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    
    await create_domain_groups(
        hass,
        hass.data[DOMAIN][DOMAIN_CONFIG],
        [input_boolean.DOMAIN, light.DOMAIN]
    )
    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.all_input_boolean_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.test_power"}

    assert not hass.states.get("sensor.all_light_power")

