import logging
import time

from measure.controller.media.controller import MediaController
from measure.execution import ImmediateInteraction, RunInteraction, SpeakerOperatingPoint
from measure.powermeter.errors import ZeroReadingError
from measure.request import SpeakerMeasurementRequest
from measure.runner.runner import MeasurementRunner, RunnerResult
from measure.tuning import MeasurementParameters
from measure.util.measure_util import MeasurementResult, MeasureUtil

DURATION_PER_VOLUME_LEVEL = 20
STREAM_URL = "https://powercalc.s3.eu-west-1.amazonaws.com/g_pink.mp3"
SLEEP_PRE_MEASURE = 2
SLEEP_MUTE = 5

_LOGGER = logging.getLogger("measure")


class SpeakerRunner(MeasurementRunner[SpeakerMeasurementRequest]):
    def __init__(
        self,
        measure_util: MeasureUtil,
        parameters: MeasurementParameters,
        media_controller: MediaController,
        interaction: RunInteraction | None = None,
    ) -> None:
        self.measure_util = measure_util
        self.config = parameters
        self.media_controller = media_controller
        self.interaction = interaction or ImmediateInteraction()

    def run(
        self,
        request: SpeakerMeasurementRequest,
        export_directory: str,
    ) -> RunnerResult:
        summary = {}
        voltages: list[float] = []
        duration = DURATION_PER_VOLUME_LEVEL

        self.interaction.notify(
            f"Prepare to start measuring the power for {duration} seconds on each volume level "
            "starting with 10 until 100 (with steps of 10 between)",
        )
        self.interaction.confirm(
            "Speaker measurements can become very loud at higher volume levels. "
            "Wear hearing protection or move to another room before starting.",
        )
        self.interaction.phase("Starting speaker measurement")
        self.interaction.progress(0, 11, phase="Measuring volume levels", remaining_seconds=self._remaining_seconds(0))

        disable_streaming = request.disable_streaming

        for volume in range(10, 101, 10):
            _LOGGER.info("Setting volume to %d", volume)
            self.media_controller.set_volume(volume)
            self.interaction.operating_point(SpeakerOperatingPoint(type="speaker", volume=volume, muted=False))
            if not disable_streaming:
                _LOGGER.info("Start streaming noise")
                self.media_controller.play_audio(STREAM_URL)
            self.interaction.phase(f"Stabilizing speaker at {volume}% volume")
            self.interaction.wait(SLEEP_PRE_MEASURE)
            self.interaction.phase(f"Measuring speaker at {volume}% volume")
            result = self.measure_util.take_average_measurement(duration)
            summary[volume] = result.power
            voltages.extend(result.voltages)
            self.interaction.progress(
                volume // 10,
                11,
                phase="Measuring volume levels",
                remaining_seconds=self._remaining_seconds(volume // 10),
            )

        _LOGGER.info("Muting volume and waiting for %d seconds", SLEEP_MUTE)
        self.media_controller.mute_volume()
        self.interaction.operating_point(SpeakerOperatingPoint(type="speaker", volume=0, muted=True))
        self.interaction.phase("Stabilizing muted speaker")
        self.interaction.wait(SLEEP_MUTE)
        self.interaction.phase("Measuring muted speaker")
        result = self.measure_util.take_average_measurement(duration)
        summary[0] = result.power
        voltages.extend(result.voltages)
        self.interaction.progress(11, 11, phase="Measuring volume levels", remaining_seconds=0)

        self.media_controller.set_volume(10)
        self.interaction.operating_point(SpeakerOperatingPoint(type="speaker", volume=10, muted=False))

        self.interaction.notify("Summary of all average measurements:")
        for volume in summary:
            self.interaction.notify(f"{volume} : {summary[volume]}")

        return RunnerResult(model_json_data=self._build_model_json_data(summary), voltages=voltages)

    @staticmethod
    def _remaining_seconds(completed_levels: int) -> float:
        """Estimated time for the remaining volume levels plus the muted baseline."""
        remaining_levels = 10 - completed_levels
        return (
            remaining_levels * (SLEEP_PRE_MEASURE + DURATION_PER_VOLUME_LEVEL) + SLEEP_MUTE + DURATION_PER_VOLUME_LEVEL
        )

    @staticmethod
    def _build_model_json_data(summary: dict[int, float]) -> dict[str, object]:
        calibrate_list = [f"{volume} -> {summary[volume]}" for volume in summary]

        return {
            "device_type": "smart_speaker",
            "calculation_strategy": "linear",
            "calculation_enabled_condition": "{{ is_state('[[entity]]', 'playing') }}",
            "linear_config": {"calibrate": calibrate_list},
        }

    def measure_standby_power(self) -> MeasurementResult:
        self.media_controller.turn_off()
        self.interaction.operating_point(SpeakerOperatingPoint(type="speaker", volume=0, muted=True))
        start_time = time.time()
        _LOGGER.info(
            "Measuring standby power. Waiting for %d seconds...",
            self.config.sleep_standby,
        )
        self.interaction.wait(self.config.sleep_standby)
        try:
            return self.measure_util.take_measurement(start_time)
        except ZeroReadingError:
            _LOGGER.error("Measured 0 watt as standby power.")
            return MeasurementResult(power=0, voltages=[])

    def cleanup(self) -> None:
        """Stop playback after success, failure, or cancellation."""

        try:
            self.media_controller.turn_off()
        except Exception:  # noqa: BLE001 - cleanup must not mask the measurement outcome
            _LOGGER.warning("Could not turn off speaker during cleanup", exc_info=True)
