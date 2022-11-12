import pytest
from homeassistant.components import sensor
from homeassistant.const import CONF_PLATFORM, DEVICE_CLASS_CURRENT, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import mock_registry, mock_device_registry

import custom_components.test.sensor as test_sensor_platform
from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import CONF_POWER_FACTOR, CONF_VOLTAGE, DOMAIN
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.strategy.wled import WledStrategy
from custom_components.test.light import MockLight

from ..common import create_mock_light_entity, run_powercalc_setup_yaml_config


async def test_can_calculate_power(hass: HomeAssistant):
    await create_mock_light_entity(hass, MockLight("test", STATE_ON, "abc"))

    light_source_entity = await create_source_entity("light.test", hass)

    platform: test_sensor_platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    estimated_current_entity = platform.MockSensor(
        name="test_estimated_current", native_value="50.0", unique_id="abc"
    )
    platform.ENTITIES[0] = estimated_current_entity

    assert await async_setup_component(
        hass, sensor.DOMAIN, {sensor.DOMAIN: {CONF_PLATFORM: "test"}}
    )
    await hass.async_block_till_done()

    strategy = WledStrategy(
        config={CONF_VOLTAGE: 5, CONF_POWER_FACTOR: 0.9},
        light_entity=light_source_entity,
        hass=hass,
        standby_power=0.1,
    )
    await strategy.validate_config()
    assert strategy.can_calculate_standby()

    state = State("sensor.test_estimated_current", "50.0")
    assert pytest.approx(0.225, 0.01) == float(await strategy.calculate(state))

    state = State("light.test", STATE_OFF)
    assert 0.1 == await strategy.calculate(state)

    state = State("light.test", STATE_ON)
    assert pytest.approx(0.225, 0.01) == float(await strategy.calculate(state))


async def test_find_estimated_current_entity_by_device_class(hass: HomeAssistant):
    """
    By default we will search for estimated_current entity by naming convention _estimated_current
    When none is found we check for entities on the same WLED device with device_class current
    """
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1234",
                platform="light",
                device_id="wled-device-id",
            ),
            "sensor.test_current": RegistryEntry(
                entity_id="sensor.test_current",
                unique_id="1234",
                platform="sensor",
                device_id="wled-device-id",
                unit_of_measurement="mA",
                original_device_class=DEVICE_CLASS_CURRENT,
            ),
        },
    )

    strategy = WledStrategy(
        config={CONF_VOLTAGE: 5, CONF_POWER_FACTOR: 0.9},
        light_entity=await create_source_entity("light.test", hass),
        hass=hass,
        standby_power=0.1,
    )
    estimated_current_entity = await strategy.find_estimated_current_entity()
    assert estimated_current_entity == "sensor.test_current"


async def test_exception_is_raised_when_no_estimated_current_entity_found(
    hass: HomeAssistant,
):
    with pytest.raises(StrategyConfigurationError):
        mock_registry(
            hass,
            {
                "light.test": RegistryEntry(
                    entity_id="light.test",
                    unique_id="1234",
                    platform="light",
                    device_id="wled-device-id",
                )
            },
        )

        strategy = WledStrategy(
            config={CONF_VOLTAGE: 5, CONF_POWER_FACTOR: 0.9},
            light_entity=await create_source_entity("light.test", hass),
            hass=hass,
            standby_power=0.1,
        )
        await strategy.find_estimated_current_entity()

async def test_wled_autodiscovery_flow(hass: HomeAssistant):
    mock_device_registry(
        hass,
        {
            "wled-device": DeviceEntry(
                id="wled-device", manufacturer="WLED", model="FOSS"
            )
        },
    )
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1234",
                platform="light",
                device_id="wled-device",
            ),
            "sensor.test_current": RegistryEntry(
                entity_id="sensor.test_current",
                unique_id="1234",
                platform="sensor",
                device_id="wled-device",
                unit_of_measurement="mA",
                original_device_class=DEVICE_CLASS_CURRENT,
            ),
        },
    )

    await run_powercalc_setup_yaml_config(hass, {}, {})
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1

    flow = flows[0]
    context = flow["context"]
    assert context["source"] == SOURCE_INTEGRATION_DISCOVERY
    assert flow["step_id"] == "wled"

    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {CONF_VOLTAGE: 5})
    assert result["type"] == FlowResultType.CREATE_ENTRY
