from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
import voluptuous as vol

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import CalculationStrategy
from custom_components.powercalc.errors import StrategyConfigurationError
from custom_components.powercalc.power_profile.power_profile import PowerProfile
from custom_components.powercalc.strategy.battery_rate import CONFIG_SCHEMA, BatteryRateStrategy
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory
from tests.common import assert_entity_state, mock_devices, mock_entities_in_registry, run_powercalc_setup, set_states

START = datetime(2026, 11, 1, tzinfo=UTC)
BATTERY_CONFIG = {"entity_id": "sensor.battery", "energy_per_percent": 0.96, "base_power": 3.5}


def create_strategy(hass: HomeAssistant, max_power: Decimal | None = None) -> BatteryRateStrategy:
    config = dict(BATTERY_CONFIG)
    if max_power is not None:
        config["max_power"] = max_power
    return BatteryRateStrategy(hass, config)


def test_window_uses_step_held_values_and_full_denominator(hass: HomeAssistant) -> None:
    strategy = create_strategy(hass)
    assert strategy.calculate_power(START) is None
    strategy.record_reading(START, Decimal(20))
    assert strategy.calculate_power(START) == Decimal("3.5")
    strategy.record_reading(START + timedelta(minutes=2), Decimal(21))
    assert strategy.calculate_power(START + timedelta(minutes=2)) == Decimal("9.26")
    strategy.record_reading(START + timedelta(minutes=7), Decimal(24))
    assert strategy.calculate_power(START + timedelta(minutes=10)) == Decimal("26.54")
    assert strategy.calculate_power(START + timedelta(minutes=12)) == Decimal("20.78")
    assert strategy.calculate_power(START + timedelta(minutes=17)) == Decimal("3.5")


def test_constant_rate_and_complete_tail_preserve_energy(hass: HomeAssistant) -> None:
    strategy = create_strategy(hass)
    strategy.record_reading(START, Decimal(0))
    energy = Decimal(0)
    for minute in range(70):
        now = START + timedelta(minutes=minute)
        strategy.record_reading(now, Decimal(min(minute, 60)))
        power = strategy.calculate_power(now)
        assert power is not None
        energy += (power - Decimal("3.5")) / 60
        if 10 <= minute < 60:
            assert power == Decimal("61.10")
    assert energy == Decimal("57.6")  # 60 displayed percent at 0.96 Wh/%


@pytest.mark.parametrize("invalid", [None, Decimal(-1), Decimal(101), Decimal("NaN"), Decimal("Infinity")])
def test_invalid_reading_breaks_history(hass: HomeAssistant, invalid: Decimal | None) -> None:
    strategy = create_strategy(hass)
    strategy.record_reading(START, Decimal(20))
    strategy.record_reading(START + timedelta(minutes=1), Decimal(25))
    strategy.record_reading(START + timedelta(minutes=2), invalid)
    assert strategy.calculate_power(START + timedelta(minutes=2)) is None
    strategy.record_reading(START + timedelta(minutes=3), Decimal(40))
    assert strategy.calculate_power(START + timedelta(minutes=3)) == Decimal("3.5")


def test_drop_limit_duplicate_and_clock_reset(hass: HomeAssistant) -> None:
    strategy = create_strategy(hass, Decimal(60))
    strategy.record_reading(START, Decimal(20))
    strategy.record_reading(START, Decimal(21))
    strategy.record_reading(START + timedelta(minutes=1), Decimal(40))
    assert strategy.calculate_power(START + timedelta(minutes=1)) == 60
    strategy.record_reading(START + timedelta(minutes=2), Decimal(19))
    assert strategy.calculate_power(START + timedelta(minutes=2)) == Decimal("3.5")
    strategy.record_reading(START + timedelta(minutes=3), Decimal(19))
    strategy.record_reading(START - timedelta(seconds=1), Decimal(30))
    assert strategy.calculate_power(START) == Decimal("3.5")


@pytest.mark.parametrize(
    "overrides",
    [
        {"entity_id": "invalid"},
        {"energy_per_percent": 0},
        {"energy_per_percent": -1},
        {"energy_per_percent": "nan"},
        {"energy_per_percent": "invalid"},
        {"energy_per_percent": []},
        {"base_power": -1},
        {"window": 0},
        {"window": -1},
        {"window": "inf"},
        {"window": 1e300},
        {"window": 1e-10},
        {"max_power": 3},
        {"unknown": 1},
    ],
)
def test_invalid_config(overrides: dict[str, Any]) -> None:
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA({**BATTERY_CONFIG, **overrides})


@pytest.mark.parametrize("missing", ["entity_id", "energy_per_percent"])
def test_required_config(missing: str) -> None:
    config = dict(BATTERY_CONFIG)
    config.pop(missing)
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA(config)


async def test_factory_profile_and_cold_restart(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    profile = PowerProfile(
        hass, "test", "battery", "", {"calculation_strategy": "battery_rate", "battery_rate_config": BATTERY_CONFIG}
    )
    factory = PowerCalculatorStrategyFactory(hass)
    source = create_source_entity("vacuum.robot", hass)
    state = State("vacuum.robot", "docked")
    strategy = await factory.create({}, CalculationStrategy.BATTERY_RATE, profile, source)
    assert strategy.get_update_interval() == timedelta(seconds=60)
    await strategy.async_update_state()
    assert await strategy.calculate(state) is None
    await set_states(hass, [("sensor.battery", "20")])
    await strategy.async_update_state()
    freezer.tick(60)
    await set_states(hass, [("sensor.battery", "21")])
    await strategy.async_update_state()
    assert await strategy.calculate(state) == Decimal("9.26")
    restarted = await factory.create({}, CalculationStrategy.BATTERY_RATE, profile, source)
    await restarted.async_update_state()
    assert await restarted.calculate(state) == Decimal("3.5")


async def test_factory_rejects_invalid_raw_profile(hass: HomeAssistant) -> None:
    with pytest.raises(StrategyConfigurationError, match="Invalid battery_rate"):
        BatteryRateStrategy(hass, {**BATTERY_CONFIG, "window": 0})


@pytest.mark.parametrize("invalid", ["unknown", "unavailable", "not numeric", "nan", "101"])
async def test_strategy_clears_invalid_state(hass: HomeAssistant, invalid: str) -> None:
    strategy = BatteryRateStrategy(hass, {**BATTERY_CONFIG, "window": 30, "max_power": 60})
    assert strategy.get_update_interval() == timedelta(seconds=30)
    assert strategy.get_entities_to_track() == ["sensor.battery"]
    await set_states(hass, [("sensor.battery", "20")])
    await strategy.async_update_state()
    await set_states(hass, [("sensor.battery", invalid)])
    await strategy.async_update_state()
    assert await strategy.calculate(State("vacuum.robot", "docked")) is None
    await set_states(hass, [("sensor.battery", "30")])
    await strategy.async_update_state()
    assert await strategy.calculate(State("vacuum.robot", "docked")) == Decimal("3.5")


async def advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int) -> None:
    freezer.tick(seconds)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_standalone_yaml_tracks_battery_and_decays_without_events(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await set_states(hass, [("sensor.battery", "20"), ("vacuum.robot", "docked")])
    await run_powercalc_setup(hass, {"entity_id": "vacuum.robot", "battery_rate": BATTERY_CONFIG, "multiply_factor": 2})
    assert_entity_state(hass, "sensor.robot_power", "7.00")
    await advance(hass, freezer, 60)
    await set_states(hass, [("sensor.battery", "25")])
    assert_entity_state(hass, "sensor.robot_power", "64.60")
    await advance(hass, freezer, 601)
    assert_entity_state(hass, "sensor.robot_power", "7.00")


@pytest.mark.parametrize("mode", ["stop_at_first", "sum_all", "list"])
async def test_composite_transitions_keep_history_and_tail_at_full(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, mode: str
) -> None:
    strategies = [
        {
            "condition": {"condition": "state", "state": "docked"},
            "battery_rate": BATTERY_CONFIG,
        },
        {"fixed": {"power": 2}},
    ]
    composite: list[ConfigType] | ConfigType = (
        strategies if mode == "list" else {"mode": mode, "strategies": strategies}
    )
    await set_states(hass, [("sensor.battery", "95"), ("vacuum.robot", "docked")])
    await run_powercalc_setup(hass, {"entity_id": "vacuum.robot", "composite": composite})
    await advance(hass, freezer, 60)
    await set_states(hass, [("sensor.battery", "100")])
    assert_entity_state(hass, "sensor.robot_power", "34.30" if mode == "sum_all" else "32.30")
    await set_states(hass, [("vacuum.robot", "cleaning")])
    assert_entity_state(hass, "sensor.robot_power", "2.00")
    await advance(hass, freezer, 60)
    await set_states(hass, [("vacuum.robot", "docked")])
    assert_entity_state(hass, "sensor.robot_power", "34.30" if mode == "sum_all" else "32.30")
    await advance(hass, freezer, 601)
    assert_entity_state(hass, "sensor.robot_power", "5.50" if mode == "sum_all" else "3.50")


async def test_history_collected_behind_first_matching_branch(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    await set_states(hass, [("sensor.battery", "20"), ("vacuum.robot", "washing")])
    await run_powercalc_setup(
        hass,
        {
            "entity_id": "vacuum.robot",
            "composite": [
                {"condition": {"condition": "state", "state": "washing"}, "fixed": {"power": 100}},
                {"battery_rate": BATTERY_CONFIG},
            ],
        },
    )
    await advance(hass, freezer, 60)
    await set_states(hass, [("sensor.battery", "21")])
    assert_entity_state(hass, "sensor.robot_power", "100.00")
    await set_states(hass, [("vacuum.robot", "docked")])
    assert_entity_state(hass, "sensor.robot_power", "9.26")


async def test_periodic_updates_preserve_standby_and_sleep(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await set_states(hass, [("sensor.battery", "20"), ("switch.charger", "on")])
    await run_powercalc_setup(
        hass,
        {
            "entity_id": "switch.charger",
            "battery_rate": BATTERY_CONFIG,
            "standby_power": 2,
            "sleep_power": {"power": 1, "delay": 120},
        },
    )
    await set_states(hass, [("switch.charger", "off")])
    await advance(hass, freezer, 61)
    assert_entity_state(hass, "sensor.charger_power", "2.00")
    await advance(hass, freezer, 61)
    assert_entity_state(hass, "sensor.charger_power", "1.00")
    await advance(hass, freezer, 61)
    assert_entity_state(hass, "sensor.charger_power", "1.00")
    await set_states(hass, [("switch.charger", "on")])
    assert_entity_state(hass, "sensor.charger_power", "3.50")


@pytest.mark.parametrize("shape", ["standalone", "list", "object"])
async def test_profile_resolves_battery_placeholder(hass: HomeAssistant, tmp_path: Path, shape: str) -> None:
    mock_devices(hass, {"robot": {"manufacturer": "test", "model": "battery"}})
    mock_entities_in_registry(
        hass,
        {
            "vacuum.robot": {"device_id": "robot", "platform": "test"},
            "sensor.battery": {"device_id": "robot", "platform": "test", "original_device_class": "battery"},
        },
    )
    config = {**BATTERY_CONFIG, "entity_id": "[[entity_by_device_class:battery]]"}
    profile: ConfigType = {"name": "Battery", "device_type": "vacuum_robot"}
    if shape == "standalone":
        profile.update({"calculation_strategy": "battery_rate", "battery_rate_config": config})
    else:
        branches = [{"battery_rate": config}]
        profile.update(
            {
                "calculation_strategy": "composite",
                "composite_config": branches if shape == "list" else {"mode": "sum_all", "strategies": branches},
            }
        )
    (tmp_path / "model.json").write_text(json.dumps(profile))
    await set_states(hass, [("vacuum.robot", "docked"), ("sensor.battery", "20")])
    await run_powercalc_setup(hass, {"entity_id": "vacuum.robot", "custom_model_directory": str(tmp_path)})
    assert_entity_state(hass, "sensor.robot_power", "3.50")
    await set_states(hass, [("sensor.battery", "21")])
    assert_entity_state(hass, "sensor.robot_power", "9.26")


async def test_strategy_timer_follows_subprofile_and_is_removed(
    hass: HomeAssistant, tmp_path: Path, freezer: FrozenDateTimeFactory
) -> None:
    root = {"name": "Battery", "device_type": "vacuum_robot", "calculation_strategy": "composite"}
    (tmp_path / "model.json").write_text(json.dumps(root))
    for name, branch in {
        "initial": {"battery_rate": BATTERY_CONFIG},
        "short": {"battery_rate": {**BATTERY_CONFIG, "window": 30}},
        "fixed": {"fixed": {"power": 2}},
    }.items():
        directory = tmp_path / name
        directory.mkdir()
        (directory / "model.json").write_text(json.dumps({"composite_config": [branch]}))
    await set_states(hass, [("vacuum.robot", "docked"), ("sensor.battery", "20")])
    await run_powercalc_setup(
        hass,
        {"entity_id": "vacuum.robot", "model": "battery/initial", "custom_model_directory": str(tmp_path)},
    )
    for profile in ["short", "fixed", "short"]:
        await hass.services.async_call(
            "powercalc", "switch_sub_profile", {"entity_id": "sensor.robot_power", "profile": profile}, blocking=True
        )
        assert_entity_state(hass, "sensor.robot_power", "2.00" if profile == "fixed" else "3.50")
        if profile == "fixed":
            await advance(hass, freezer, 61)
            assert_entity_state(hass, "sensor.robot_power", "2.00")
    await advance(hass, freezer, 1)
    await set_states(hass, [("sensor.battery", "21")])
    assert_entity_state(hass, "sensor.robot_power", "118.70")
    await advance(hass, freezer, 31)
    assert_entity_state(hass, "sensor.robot_power", "3.50")
    entity = hass.data["sensor"].get_entity("sensor.robot_power")
    assert entity is not None
    await entity.async_remove()
    await advance(hass, freezer, 61)
    assert hass.states.get("sensor.robot_power") is None
