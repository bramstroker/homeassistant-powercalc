import logging

from homeassistant.components.fan import ATTR_PERCENTAGE
from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.components.media_player import ATTR_MEDIA_VOLUME_LEVEL
from homeassistant.components.mqtt.vacuum import STATE_DOCKED
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONF_ATTRIBUTE,
    CONF_ENTITY_ID,
    STATE_ON,
    STATE_PAUSED,
    STATE_PLAYING,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, RegistryEntryWithDefaults, mock_device_registry, mock_registry

from custom_components.powercalc.common import SourceEntity, create_source_entity
from custom_components.powercalc.const import (
    CONF_CALIBRATE,
    CONF_LINEAR,
    CONF_MAX_POWER,
    CONF_MIN_POWER,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SensorType,
)
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.strategy.linear import LinearStrategy
from tests.conftest import MockEntityWithModel


async def test_light_max_power_only(hass: HomeAssistant) -> None:
    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("light.test", hass),
        {CONF_MAX_POWER: 255},
    )

    state = State("light.test", STATE_ON, {ATTR_BRIGHTNESS: 100})
    assert await strategy.calculate(state) == 100


async def test_fan_min_and_max_power(hass: HomeAssistant) -> None:
    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("fan.test", hass),
        {CONF_MIN_POWER: 10, CONF_MAX_POWER: 100},
    )

    state = State("fan.test", STATE_ON, {ATTR_PERCENTAGE: 50})
    assert await strategy.calculate(state) == 55


async def test_light_calibrate(hass: HomeAssistant) -> None:
    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("light.test", hass),
        {
            CONF_CALIBRATE: [
                "1 -> 0.3",
                "10 -> 1.25",
                "50 -> 3.50",
                "100 -> 6.8",
                "255 -> 15.3",
            ],
        },
    )

    entity_id = "light.test"
    assert (
        await strategy.calculate(
            State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 1}),
        )
        == 0.3
    )
    assert (
        await strategy.calculate(
            State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 10}),
        )
        == 1.25
    )
    assert (
        await strategy.calculate(
            State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 30}),
        )
        == 2.375
    )
    assert (
        await strategy.calculate(
            State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 75}),
        )
        == 5.15
    )
    assert (
        await strategy.calculate(
            State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 255}),
        )
        == 15.3
    )

    # set to some out of bound brightness.
    assert (
        await strategy.calculate(
            State(entity_id, STATE_ON, {ATTR_BRIGHTNESS: 350}),
        )
        == 15.3
    )


async def _setup_vacuum_test(hass: HomeAssistant) -> None:
    """Set up the vacuum device and entities for testing."""
    mock_device_registry(
        hass,
        {
            "vacuum-device": DeviceEntry(
                id="vacuum-device",
                manufacturer="test",
                model="test",
            ),
        },
    )
    mock_registry(
        hass,
        {
            "vacuum.test": RegistryEntryWithDefaults(
                entity_id="vacuum.test",
                unique_id="1111",
                platform="test",
                device_id="vacuum-device",
            ),
            "sensor.test_battery": RegistryEntryWithDefaults(
                entity_id="sensor.test_battery",
                unique_id="2222",
                platform="sensor",
                device_id="vacuum-device",
                original_device_class=SensorDeviceClass.BATTERY,
            ),
        },
    )


async def test_vacuum_battery_level(
    hass: HomeAssistant,
) -> None:
    await _setup_vacuum_test(hass)

    hass.states.async_set("sensor.test_battery", 50)
    await hass.async_block_till_done()

    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("vacuum.test", hass),
        {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
    )

    state = State("vacuum.test", STATE_DOCKED)
    assert await strategy.calculate(state) == 60


async def test_no_battery_entity_for_vacuum(
    hass: HomeAssistant,
) -> None:
    # Use a modified setup without the battery entity
    mock_device_registry(
        hass,
        {
            "vacuum-device": DeviceEntry(
                id="vacuum-device",
                manufacturer="test",
                model="test",
            ),
        },
    )
    mock_registry(
        hass,
        {
            "vacuum.test": RegistryEntryWithDefaults(
                entity_id="vacuum.test",
                unique_id="1111",
                platform="test",
                device_id="vacuum-device",
            ),
        },
    )

    with pytest.raises(StrategyConfigurationError, match="No battery entity found for vacuum cleaner"):
        await _create_strategy_instance(
            hass,
            await create_source_entity("vacuum.test", hass),
            {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
        )


async def test_custom_attribute(hass: HomeAssistant) -> None:
    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("fan.test", hass),
        {CONF_ATTRIBUTE: "my_attribute", CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
    )

    state = State("fan.test", STATE_ON, {"my_attribute": 40})
    assert await strategy.calculate(state) == 52


async def test_power_is_none_when_state_is_none(hass: HomeAssistant) -> None:
    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("light.test", hass),
        {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
    )

    state = State("light.test", STATE_ON, {ATTR_BRIGHTNESS: None})
    assert not await strategy.calculate(state)


async def test_error_on_non_number_state(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("sensor.test", hass),
        {CONF_CALIBRATE: ["1 -> 0.3", "10 -> 1.25"]},
    )

    state = State("sensor.test", "foo")
    assert not await strategy.calculate(state)
    assert "Expecting state to be a number for entity" in caplog.text


async def test_validate_raises_exception_not_allowed_domain(
    hass: HomeAssistant,
) -> None:
    with pytest.raises(StrategyConfigurationError):
        await _create_strategy_instance(
            hass,
            await create_source_entity("sensor.test", hass),
            {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
        )


async def test_validate_raises_exception_when_min_power_higher_than_max(
    hass: HomeAssistant,
) -> None:
    with pytest.raises(StrategyConfigurationError):
        await _create_strategy_instance(
            hass,
            await create_source_entity("light.test", hass),
            {CONF_MIN_POWER: 150, CONF_MAX_POWER: 100},
        )


async def test_lower_value_than_calibration_table_defines(hass: HomeAssistant) -> None:
    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("light.test", hass),
        {
            CONF_CALIBRATE: [
                "50 -> 5",
                "100 -> 8",
                "255 -> 15",
            ],
        },
    )
    state = State("light.test", STATE_ON, {ATTR_BRIGHTNESS: 20})
    assert pytest.approx(float(await strategy.calculate(state)), 0.01) == 3.52


async def _create_strategy_instance(
    hass: HomeAssistant,
    source_entity: SourceEntity,
    linear_config: ConfigType,
) -> LinearStrategy:
    strategy = LinearStrategy(
        source_entity=source_entity,
        config=linear_config,
        hass=hass,
        standby_power=None,
    )

    await strategy.validate_config()
    await strategy.initialize()

    return strategy


async def test_config_entry_with_calibrate_list(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information("light.test")

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_LINEAR: {CONF_CALIBRATE: {"1": 0.4, "25": 1.2, "100": 3, "255": 5.3}},
        },
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("light.test", STATE_ON, {ATTR_BRIGHTNESS: 25})
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_power")
    assert state
    assert state.state == "1.20"


async def test_media_player_volume_level(hass: HomeAssistant) -> None:
    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("media_player.test", hass),
        {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
    )

    state = State("media_player.test", STATE_PLAYING, {ATTR_MEDIA_VOLUME_LEVEL: 0.5})
    assert await strategy.calculate(state) == 60


async def test_error_is_raised_on_unsupported_entity_domain(
    hass: HomeAssistant,
) -> None:
    with pytest.raises(StrategyConfigurationError):
        await _create_strategy_instance(
            hass,
            await create_source_entity("input_boolean.test", hass),
            {CONF_MAX_POWER: 255},
        )


async def test_value_entity_not_found(
    hass: HomeAssistant,
) -> None:
    """Test that None is returned when the value entity is not found."""
    await _setup_vacuum_test(hass)

    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("vacuum.test", hass),
        {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
    )

    assert await strategy.calculate(State("light.test", STATE_ON)) is None


async def test_value_entity_state_not_found(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that None is returned when the value entity state is not found in Home Assistant."""
    caplog.set_level(logging.ERROR)
    await _setup_vacuum_test(hass)

    strategy = await _create_strategy_instance(
        hass,
        await create_source_entity("vacuum.test", hass),
        {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
    )

    state = State("vacuum.test", STATE_DOCKED)
    assert await strategy.calculate(state) is None

    assert "Value entity sensor.test_battery not found" in caplog.text


@pytest.mark.parametrize(
    "source_entity,state,expected_result",
    [
        (
            SourceEntity(object_id="test", entity_id="media_player.test", domain="media_player"),
            State("media_player.test", STATE_PLAYING, {ATTR_MEDIA_VOLUME_LEVEL: 0.5}),
            True,
        ),
        (
            SourceEntity(object_id="test", entity_id="media_player.test", domain="media_player"),
            State("media_player.test", STATE_PAUSED),
            False,
        ),
    ],
)
async def test_is_enabled(hass: HomeAssistant, source_entity: SourceEntity, state: State, expected_result: bool) -> None:
    strategy = await _create_strategy_instance(
        hass,
        source_entity,
        {CONF_MIN_POWER: 20, CONF_MAX_POWER: 100},
    )
    assert strategy.is_enabled(state) is expected_result
