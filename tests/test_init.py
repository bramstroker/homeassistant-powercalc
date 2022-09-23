import logging

from unittest.mock import AsyncMock, call, patch
import pytest
from homeassistant.components import input_boolean, light
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_MODE, ColorMode
from homeassistant.config_entries import ConfigEntryState, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import (
    EntityRegistry,
    RegistryEntry,
    RegistryEntryDisabler,
)
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc import create_domain_groups
from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENABLE_AUTODISCOVERY,
    CONF_FIXED,
    CONF_MANUFACTURER,
    CONF_MODEL,
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


@pytest.fixture
def mock_flow_init(hass):
    """Mock hass.config_entries.flow.async_init."""
    with patch.object(
        hass.config_entries.flow, "async_init", return_value=AsyncMock()
    ) as mock_init:
        yield mock_init


async def test_autodiscovery(hass: HomeAssistant, mock_flow_init):
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

    # Check that two discovery flows have been initialized
    # LightA and LightB should be discovered, LightC not
    assert mock_flow_init.mock_calls == [
        call(
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data={
                CONF_UNIQUE_ID: lighta.unique_id,
                CONF_NAME: lighta.name,
                CONF_ENTITY_ID: lighta.entity_id,
                CONF_MANUFACTURER: lighta.manufacturer,
                CONF_MODEL: lighta.model,
            }
        ),
        call(
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data={
                CONF_UNIQUE_ID: lightb.unique_id,
                CONF_NAME: lightb.name,
                CONF_ENTITY_ID: lightb.entity_id,
                CONF_MANUFACTURER: lightb.manufacturer,
                CONF_MODEL: lightb.model,
            }
        )
    ]

    # Also check if power sensors are created.
    # Currently, we also create them directly, even without the user finishing the discovery flow
    # In the future this behaviour may change.
    assert hass.states.get("sensor.testa_power")
    assert hass.states.get("sensor.testb_power")
    assert not hass.states.get("sensor.testc_power")


async def test_discovery_skipped_when_confirmed_by_user(hass: HomeAssistant, mock_flow_init):
    light_entity = MockLight("test")
    light_entity.manufacturer = "lidl"
    light_entity.model = "HG06106C"
    await create_mock_light_entity(hass, light_entity)

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_UNIQUE_ID: light_entity.unique_id,
            CONF_NAME: light_entity.name,
            CONF_ENTITY_ID: light_entity.entity_id,
            CONF_MANUFACTURER: light_entity.manufacturer,
            CONF_MODEL: light_entity.model,
        },
        source=SOURCE_INTEGRATION_DISCOVERY,
        unique_id=light_entity.unique_id
    )
    config_entry.add_to_hass(hass)

    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert not mock_flow_init.mock_calls


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
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_autodiscovery_skipped_for_lut_with_subprofiles(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    """
    Lights which can be autodiscovered and have sub profiles need to de skipped
    User needs to configure this because we cannot know which sub profile to select
    No power sensor should be created and no error should appear in the logs
    """
    caplog.set_level(logging.ERROR)

    light_entity = MockLight("testa")
    light_entity.manufacturer = "Yeelight"
    light_entity.model = "strip6"
    light_entity.supported_color_modes = [ColorMode.COLOR_TEMP, ColorMode.HS]
    await create_mock_light_entity(hass, light_entity)

    await async_setup_component(
        hass, DOMAIN, {DOMAIN: {CONF_ENABLE_AUTODISCOVERY: True}}
    )
    await hass.async_block_till_done()

    assert not hass.states.get("sensor.testa_power")
    assert not caplog.records


async def test_manual_configured_light_overrides_autodiscovered(hass: HomeAssistant):
    light_entity = MockLight("testing")
    light_entity.manufacturer = "signify"
    light_entity.model = "LCA001"
    await create_mock_light_entity(hass, light_entity)

    await run_powercalc_setup_yaml_config(
        hass, {CONF_ENTITY_ID: "light.testing", CONF_FIXED: {CONF_POWER: 25}}, {}
    )

    state = hass.states.get("sensor.testing_power")
    assert state
    assert state.state == "25.00"


async def test_config_entry_overrides_autodiscovered(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)

    light_entity = MockLight("testing", unique_id="abcdef")
    light_entity.manufacturer = "signify"
    light_entity.model = "LWA017"
    light_entity.color_mode = ColorMode.BRIGHTNESS
    await create_mock_light_entity(hass, light_entity)

    hass.states.async_set(
        "light.testing",
        STATE_ON,
        {ATTR_BRIGHTNESS: 200, ATTR_COLOR_MODE: ColorMode.BRIGHTNESS},
    )

    await run_powercalc_setup_yaml_config(hass, {}, {})

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_NAME: "testing",
            CONF_ENTITY_ID: "light.testing",
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LWA017",
        },
        unique_id="abcdef",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testing_power")
    assert not caplog.records


async def test_autodiscover_skips_disabled_entities(hass: HomeAssistant):
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1234",
                platform="light",
                device_id="some-device-id",
                disabled_by=RegistryEntryDisabler.HASS,
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "light.test": DeviceEntry(
                id="some-device-id", manufacturer="signify", model="LCT010"
            )
        },
    )
    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert not hass.states.get("sensor.test_power")


async def test_autodiscover_skips_entities_with_empty_manufacturer(hass: HomeAssistant):
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1234",
                platform="light",
                device_id="some-device-id",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            "light.test": DeviceEntry(
                id="some-device-id", manufacturer="", model="LCT010"
            )
        },
    )
    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert not hass.states.get("sensor.test_power")


async def test_domain_groups(hass: HomeAssistant, entity_reg: EntityRegistry):
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

    entity_entry = entity_reg.async_get("sensor.all_input_boolean_power")
    assert entity_entry
    assert entity_entry.platform == "powercalc"


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
