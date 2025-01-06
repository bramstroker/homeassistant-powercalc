import logging

import pytest
from homeassistant.components import sensor
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntry
from homeassistant.const import CONF_ENTITY_ID, CONF_PLATFORM, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    mock_device_registry,
    mock_registry,
)

import custom_components.test.sensor as test_sensor_platform
from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_POWER_FACTOR,
    CONF_VOLTAGE,
    CONF_WLED,
    DOMAIN,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.strategy.wled import WledStrategy
from tests.common import run_powercalc_setup
from tests.conftest import MockEntityWithModel


async def test_can_calculate_power(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information("light.test")
    hass.states.async_set("light.test", STATE_ON)
    await hass.async_block_till_done()

    light_source_entity = await create_source_entity("light.test", hass)

    platform: test_sensor_platform = getattr(hass.components, "test.sensor")
    platform.init(empty=True)
    estimated_current_entity = platform.MockSensor(
        name="test_estimated_current",
        native_value="50.0",
        unique_id="abc",
    )
    platform.ENTITIES[0] = estimated_current_entity

    assert await async_setup_component(
        hass,
        sensor.DOMAIN,
        {sensor.DOMAIN: {CONF_PLATFORM: "test"}},
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
    assert await strategy.calculate(state) == 0.1

    state = State("light.test", STATE_ON)
    assert pytest.approx(0.225, 0.01) == float(await strategy.calculate(state))


async def test_find_estimated_current_entity_by_device_class(
    hass: HomeAssistant,
) -> None:
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
                original_device_class=SensorDeviceClass.CURRENT,
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
) -> None:
    with pytest.raises(StrategyConfigurationError):
        mock_registry(
            hass,
            {
                "light.test": RegistryEntry(
                    entity_id="light.test",
                    unique_id="1234",
                    platform="light",
                    device_id="wled-device-id",
                ),
            },
        )

        strategy = WledStrategy(
            config={CONF_VOLTAGE: 5, CONF_POWER_FACTOR: 0.9},
            light_entity=await create_source_entity("light.test", hass),
            hass=hass,
            standby_power=0.1,
        )
        await strategy.find_estimated_current_entity()


async def test_wled_autodiscovery_flow(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    mock_device_registry(
        hass,
        {
            "wled-device": DeviceEntry(
                id="wled-device",
                manufacturer="WLED",
                model="FOSS",
            ),
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
            "light.test_master": RegistryEntry(
                entity_id="light.test_master",
                unique_id="1234-master",
                platform="light",
                original_name="Master",
                device_id="wled-device",
            ),
            "light.test_segment1": RegistryEntry(
                entity_id="light.test_segment1",
                unique_id="1234-segment",
                platform="light",
                original_name="WLED Segment1",
                device_id="wled-device",
            ),
            "light.test_segment_1_2": RegistryEntry(
                entity_id="light.test_segment_1_2",
                unique_id="1234-segment",
                platform="light",
                device_id="wled-device",
            ),
            "sensor.test_current": RegistryEntry(
                entity_id="sensor.test_current",
                unique_id="1234",
                platform="sensor",
                device_id="wled-device",
                unit_of_measurement="mA",
                original_device_class=SensorDeviceClass.CURRENT,
            ),
        },
    )

    await run_powercalc_setup(hass, {}, {})
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1

    flow = flows[0]
    context = flow["context"]
    assert context["source"] == SOURCE_INTEGRATION_DISCOVERY
    assert flow["step_id"] == Step.WLED

    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"],
        {CONF_VOLTAGE: 5},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry: ConfigEntry = result["result"]
    assert entry.unique_id == "pc_wled-device"

    assert len(caplog.records) == 0


async def test_yaml_configuration(hass: HomeAssistant) -> None:
    """
    Full functional test for YAML configuration setup.
    Also check standby power can be calculated by the WLED strategy
    """
    mock_device_registry(
        hass,
        {
            "wled-device": DeviceEntry(
                id="wled-device",
                manufacturer="WLED",
                model="FOSS",
            ),
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
                original_device_class=SensorDeviceClass.CURRENT,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_WLED: {
                CONF_VOLTAGE: 5,
                CONF_POWER_FACTOR: 1,
            },
        },
    )

    hass.states.async_set("light.test", STATE_ON)
    hass.states.async_set("sensor.test_current", 500)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "2.50"

    hass.states.async_set("light.test", STATE_OFF)
    hass.states.async_set("sensor.test_current", 50)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_power").state == "0.25"


async def test_estimated_current_sensor_unavailable(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test that a warning is logged when estimated current sensor is unavailable."""

    caplog.set_level(logging.WARNING)
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
                original_device_class=SensorDeviceClass.CURRENT,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "light.test",
            CONF_WLED: {
                CONF_VOLTAGE: 5,
                CONF_POWER_FACTOR: 1,
            },
        },
    )

    hass.states.async_set("sensor.test_current", STATE_UNAVAILABLE)
    hass.states.async_set("light.test", STATE_ON)
    await hass.async_block_till_done()

    assert "light.test: Estimated current entity sensor.test_current is not available" in caplog.text

    assert hass.states.get("sensor.test_power").state == STATE_UNAVAILABLE
