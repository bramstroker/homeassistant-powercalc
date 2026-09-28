import json
from pathlib import Path
from unittest.mock import MagicMock, call

from jsonschema import validate
from measure.controller.switch.hass import HassSwitchController
from measure.controller.switch.spec import HassMultiSwitchControllerSpec, HassSwitchControllerSpec
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import SmartSwitchMeasurementRequest
from measure.runner.interaction import RunInteraction
from measure.runner.smart_switch import SmartSwitchRunner
from measure.utils.sampling import MeasurementResult, PowerSampler
import pytest


def make_runner(
    entity_ids: list[str], powers: list[float]
) -> tuple[SmartSwitchRunner, MagicMock, MagicMock, MagicMock]:
    sampler = MagicMock(spec=PowerSampler)
    sampler.take_measurement.side_effect = [MeasurementResult(power=value, voltages=[230.0]) for value in powers]
    controller = MagicMock(spec=HassSwitchController)
    controller.entity_ids = entity_ids
    interaction = MagicMock(spec=RunInteraction)
    return SmartSwitchRunner(sampler, controller, interaction), sampler, controller, interaction


def make_request(entity_ids: list[str], power_monitoring: bool = False) -> SmartSwitchMeasurementRequest:
    controller = (
        HassSwitchControllerSpec(entity_id=entity_ids[0])
        if len(entity_ids) == 1
        else HassMultiSwitchControllerSpec(entity_ids=entity_ids)
    )
    return SmartSwitchMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        controller=controller,
        power_monitoring=power_monitoring,
        repeat_cycles=2,
        samples_per_state=5,
        settle_seconds=0,
    )


@pytest.mark.parametrize("power_monitoring", [False, True])
def test_single_switch_measures_both_states_and_restores_relay(tmp_path: Path, power_monitoring: bool) -> None:
    powers = [0.5] * 5 + [0.8] * 5 + [0.5] * 5 + [0.8] * 5
    runner, sampler, controller, interaction = make_runner(["switch.relay"], powers)

    result = runner.run(make_request(["switch.relay"], power_monitoring), str(tmp_path))

    assert result.model_json_data == {
        "device_type": "smart_switch",
        "device_specs": {"power_monitoring": power_monitoring},
        "calculation_strategy": "fixed",
        "standby_power": 0.5,
        "standby_power_on": 0.8,
        **({"only_self_usage": True} if power_monitoring else {}),
    }
    assert sampler.take_measurement.call_count == 20
    assert result.voltages == [230.0] * 20
    assert controller.set_states.call_args_list == [
        call(None, all_on=False),
        call("switch.relay", all_on=False),
        call(None, all_on=False),
        call("switch.relay", all_on=False),
    ]
    controller.restore_states.assert_called_once()
    assert interaction.progress.call_args_list == [
        call(0, 4, phase="Measuring relay self consumption", remaining_seconds=52),
        call(1, 4, phase="Measuring relay self consumption", remaining_seconds=39),
        call(2, 4, phase="Measuring relay self consumption", remaining_seconds=26),
        call(3, 4, phase="Measuring relay self consumption", remaining_seconds=13),
        call(4, 4, phase="Measuring relay self consumption", remaining_seconds=0),
    ]
    assert len(json.loads((tmp_path / "smart_switch_readings.json").read_text())["readings"]) == 4


def test_multi_switch_emits_multi_switch_profile(tmp_path: Path) -> None:
    ids = ["switch.one", "switch.two"]
    cycle = [0.4] * 5 + [0.6] * 5 + [0.6] * 5 + [0.8] * 5
    runner, _, controller, _ = make_runner(ids, cycle * 2)

    result = runner.run(make_request(ids), str(tmp_path))

    assert result.model_json_data == {
        "device_type": "smart_switch",
        "device_specs": {"power_monitoring": False},
        "standby_power": 0.4,
        "calculation_strategy": "multi_switch",
        "discovery_by": "device",
        "only_self_usage": True,
        "multi_switch_config": {"power": 0.2},
    }
    controller.set_states.assert_any_call(None, all_on=True)

    schema_path = Path(__file__).parents[4] / "profile_library" / "model_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validate(
        {
            "name": "Two relay test switch",
            "measure_method": "script",
            "measure_device": "External meter",
            "created_at": "2026-09-28T12:00:00Z",
            **result.model_json_data,
        },
        schema,
    )


@pytest.mark.parametrize(
    "powers, message",
    [
        ([0.0] * 5 + [0.2] * 5, "more precise meter"),
        ([0.5] * 5 + [0.4] * 5, "Relay increments differ"),
    ],
)
def test_unusable_single_switch_measurement_preserves_readings(
    tmp_path: Path, powers: list[float], message: str
) -> None:
    runner, _, controller, _ = make_runner(["switch.relay"], powers * 2)

    with pytest.raises(ValueError, match=message):
        runner.run(make_request(["switch.relay"]), str(tmp_path))

    controller.restore_states.assert_called_once()
    assert (tmp_path / "smart_switch_readings.json").exists()


def test_multi_switch_rejects_inconsistent_all_on_power(tmp_path: Path) -> None:
    ids = ["switch.one", "switch.two"]
    cycle = [0.4] * 5 + [0.6] * 5 + [0.6] * 5 + [1.3] * 5
    runner, _, controller, _ = make_runner(ids, cycle * 2)

    with pytest.raises(ValueError, match="All-on power"):
        runner.run(make_request(ids), str(tmp_path))

    controller.restore_states.assert_called_once()


def test_sampling_failure_still_restores_relay(tmp_path: Path) -> None:
    runner, sampler, controller, _ = make_runner(["switch.relay"], [])
    sampler.take_measurement.side_effect = RuntimeError("meter disconnected")

    with pytest.raises(RuntimeError, match="meter disconnected"):
        runner.run(make_request(["switch.relay"]), str(tmp_path))

    controller.restore_states.assert_called_once()


def test_cleanup_retries_restoration_without_masking_failure() -> None:
    runner, _, controller, _ = make_runner(["switch.relay"], [])

    assert runner.measure_standby_power() is None
    runner.cleanup()
    controller.restore_states.assert_called_once()

    controller.restore_states.side_effect = RuntimeError("Home Assistant offline")
    runner.cleanup()
    assert controller.restore_states.call_count == 2
