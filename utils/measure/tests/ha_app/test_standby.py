from threading import Event
from unittest.mock import MagicMock, patch

from measure.assembler import MeasurementAssembler
from measure.ha_app.light_probe import StandbyProbeStatus
from measure.ha_app.standby import StandbyMeasurement
from measure.powermeter.errors import OutdatedMeasurementError, PowerMeterError, ZeroReadingError
from measure.request import MeasurementRequest
from measure.runner.interaction import RunInteraction
from measure.utils.sampling import DummyLoadMeasurementError, MeasurementResult, NoValidReadingsError
from pydantic import TypeAdapter
import pytest


def standby_request(kind: str = "light") -> MeasurementRequest:
    controllers = {
        "light": {"type": "hass", "entity_id": "light.test"},
        "speaker": {"type": "hass", "entity_id": "media_player.test"},
        "fan": {"type": "hass", "entity_id": "fan.test"},
        "charging": {"type": "dummy"},
    }
    payload = {
        "measure_type": kind,
        "power_meter": {"type": "hass", "entity_id": "sensor.test_power", "voltage_entity_id": "sensor.test_voltage"},
        "model_id": "TEST",
        "product_name": "Test device",
        "measure_device": "Test meter",
        "parameters": {"fast_test_mode": True},
    }
    if kind in controllers:
        payload["controller"] = controllers[kind]
    if kind == "charging":
        payload["charging_device_type"] = "vacuum_robot"
    return TypeAdapter(MeasurementRequest).validate_python(payload)


@pytest.mark.parametrize("kind", ["light", "speaker", "fan", "charging", "recorder", "average"])
def test_standby_uses_device_routine_or_passive_reading(kind: str) -> None:
    request = standby_request(kind)
    assembler = MeasurementAssembler(MagicMock(spec=RunInteraction))
    controller = MagicMock()
    wait = MagicMock()
    with (
        patch.object(assembler, "create_power_meter"),
        patch.object(assembler, "create_light_controller", return_value=controller),
        patch.object(assembler, "_create_media_controller", return_value=controller),
        patch.object(assembler, "_create_fan_controller", return_value=controller),
        patch("measure.ha_app.standby.PowerSampler") as sampler,
    ):
        sampler.return_value.take_measurement.return_value = MeasurementResult(0.6, [])
        result = StandbyMeasurement(lambda: assembler, wait=wait).measure(request)
    assert result.status == StandbyProbeStatus.MEASURED
    assert result.power_w == 0.6
    if kind == "light":
        assert controller.change_light_state.call_count == 2
        controller.close.assert_called_once()
    elif kind in ["speaker", "fan"]:
        assert controller.turn_off.call_count == 2
    else:
        assert not controller.mock_calls
        wait.assert_called_once_with(request.parameters.sleep_standby)


def test_multiple_lights_are_normalized_and_calibration_reused() -> None:
    request = standby_request().model_copy(update={"multiple_light_count": 3})
    assembler = MeasurementAssembler(MagicMock(spec=RunInteraction))
    with (
        patch.object(assembler, "create_power_meter"),
        patch.object(assembler, "create_light_controller"),
        patch("measure.ha_app.standby.PowerSampler") as sampler,
    ):
        sampler.return_value.take_measurement.return_value = MeasurementResult(0.6, [])
        result = StandbyMeasurement(lambda: assembler).measure(request, 2500)
    assert result.power_w == 0.2
    sampler.return_value.set_dummy_load_resistance.assert_called_once_with(2500)


@pytest.mark.parametrize("kind", ["fan", "recorder"])
@pytest.mark.parametrize(
    "error",
    [
        ZeroReadingError("zero"),
        OutdatedMeasurementError("stale"),
        DummyLoadMeasurementError("non-positive target power"),
        NoValidReadingsError("no readings"),
    ],
)
def test_unavailable_readings_do_not_become_measurements(kind: str, error: Exception) -> None:
    assembler = MagicMock(spec=MeasurementAssembler)
    runner = assembler.create_runner.return_value
    runner.measure_standby_power.side_effect = error
    with patch("measure.ha_app.standby.PowerSampler") as sampler:
        sampler.return_value.take_measurement.side_effect = error
        result = StandbyMeasurement(lambda: assembler, wait=lambda _: None).measure(standby_request(kind))
    assert result.status == StandbyProbeStatus.UNAVAILABLE
    assert result.power_w is None
    if kind == "fan":
        runner.cleanup.assert_called_once()


@pytest.mark.parametrize("power", [None, 0, 0.04, float("nan")])
def test_invalid_standby_result_is_unavailable(power: float | None) -> None:
    assembler = MagicMock(spec=MeasurementAssembler)
    assembler.create_runner.return_value.measure_standby_power.return_value = (
        MeasurementResult(power, []) if power is not None else None
    )
    result = StandbyMeasurement(lambda: assembler).measure(standby_request())
    assert result.status == StandbyProbeStatus.UNAVAILABLE


def test_operational_failure_propagates_and_cleans_up() -> None:
    assembler = MagicMock(spec=MeasurementAssembler)
    runner = assembler.create_runner.return_value
    runner.measure_standby_power.side_effect = PowerMeterError("offline")
    measurement = StandbyMeasurement(lambda: assembler)
    request = standby_request("fan")
    with pytest.raises(PowerMeterError, match="offline"):
        measurement.measure(request)
    runner.cleanup.assert_called_once()


def test_standby_calibration_validates_voltage_and_uses_stability_flow() -> None:
    from measure.dummy_load import power_meter_fingerprint
    from measure.request import DummyLoadCalibrationRequest

    request = standby_request().model_copy(update={"dummy_load": DummyLoadCalibrationRequest(description="Heater")})
    assembler = MagicMock(spec=MeasurementAssembler)
    with (
        patch("measure.ha_app.standby.PowerSampler") as sampler,
        patch("measure.ha_app.standby.DummyLoadPreparation") as preparation,
    ):
        preparation.return_value.calibrate.return_value = 2400
        result = StandbyMeasurement(lambda: assembler).calibrate(request, Event())
    sampler.return_value.validate_dummy_load_support.assert_called_once()
    preparation.return_value.calibrate.assert_called_once()
    assert result.resistance == 2400
    assert result.description == "Heater"
    assert result.power_meter_fingerprint == power_meter_fingerprint(request.power_meter)


def test_calibration_cancellation_interrupts_sampling_wait() -> None:
    from measure.cancellation import MeasurementCancelledError
    from measure.ha_app.standby import CalibrationInteraction

    cancelled = Event()
    interaction = CalibrationInteraction(cancelled)
    interaction.checkpoint()
    interaction.wait(0)
    cancelled.set()
    with pytest.raises(MeasurementCancelledError):
        interaction.wait(30)
    assembler = MagicMock(spec=MeasurementAssembler)
    from measure.request import DummyLoadCalibrationRequest

    request = standby_request().model_copy(update={"dummy_load": DummyLoadCalibrationRequest(description="Heater")})
    with pytest.raises(MeasurementCancelledError):
        StandbyMeasurement(lambda: assembler).calibrate(request, cancelled)
    assembler.create_power_meter.assert_not_called()
