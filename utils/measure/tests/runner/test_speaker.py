from unittest.mock import MagicMock

from measure.controller.media.controller import MediaController
from measure.controller.media.spec import DummyMediaControllerSpec
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import SpeakerMeasurementRequest
from measure.runner.speaker import SpeakerRunner
from measure.tuning import MeasurementParameters
from measure.util.measure_util import MeasurementResult, MeasureUtil


def _run(media_controller: MagicMock) -> dict:
    measure_util_mock = MagicMock(MeasureUtil)
    measure_util_mock.take_average_measurement.return_value = MeasurementResult(power=10.50, voltages=[])
    runner = SpeakerRunner(measure_util_mock, MeasurementParameters(), media_controller)
    request = SpeakerMeasurementRequest(
        model_id="measurement",
        product_name="Measurement",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyMediaControllerSpec(),
    )
    return _run_and_collect(runner, request)


def _run_and_collect(runner: SpeakerRunner, request: SpeakerMeasurementRequest) -> dict:
    result = runner.run(request, "")
    return result.model_json_data


def test_run_measures_every_volume_level_and_the_muted_baseline() -> None:
    media_controller = MagicMock(MediaController)

    model_data = _run(media_controller)

    assert model_data["device_type"] == "smart_speaker"
    assert model_data["calculation_strategy"] == "linear"
    calibrate = model_data["linear_config"]["calibrate"]
    assert calibrate == [f"{volume} -> 10.5" for volume in range(10, 101, 10)] + ["0 -> 10.5"]
    assert media_controller.set_volume.call_count == 11  # 10 levels plus the reset to 10
    # The 0-volume baseline must be measured muted, not while streaming at volume 100.
    media_controller.mute_volume.assert_called_once()


def test_streaming_is_started_for_every_volume_level() -> None:
    media_controller = MagicMock(MediaController)

    _run(media_controller)

    assert media_controller.play_audio.call_count == 10
