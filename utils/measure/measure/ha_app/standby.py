from collections.abc import Callable
from threading import Event
import time

from measure.assembler import MeasurementAssembler
from measure.cancellation import MeasurementCancelledError
from measure.dummy_load import DummyLoadCalibration, power_meter_fingerprint
from measure.execution import DummyLoadPreparation
from measure.ha_app.light_probe import StandbyProbeResult, StandbyProbeStatus
from measure.powermeter.errors import OutdatedMeasurementError, ZeroReadingError
from measure.profile.standby import is_valid_standby_power
from measure.request import (
    FanMeasurementRequest,
    LightMeasurementRequest,
    MeasurementRequest,
    SpeakerMeasurementRequest,
)
from measure.runner.interaction import ImmediateInteraction
from measure.utils.clock import utc_now
from measure.utils.sampling import MeasurementError, PowerSampler


class CalibrationInteraction(ImmediateInteraction):
    """Interrupt calibration samples and waits on cancellation or app shutdown."""

    def __init__(self, cancelled: Event) -> None:
        self.cancelled = cancelled

    def checkpoint(self) -> None:
        if self.cancelled.is_set():
            raise MeasurementCancelledError("Calibration cancelled")

    def wait(self, seconds: float) -> None:
        self.cancelled.wait(seconds)
        self.checkpoint()


class StandbyMeasurement:
    """Remeasure only standby, without changing a completed session or its artifacts."""

    def __init__(
        self,
        build_assembler: Callable[[], MeasurementAssembler],
        *,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self._build_assembler = build_assembler
        self._wait = wait

    def calibrate(self, request: MeasurementRequest, cancelled: Event) -> DummyLoadCalibration:
        """Measure a preheated dummy load with the target devices disconnected."""
        assert request.dummy_load is not None
        interaction = CalibrationInteraction(cancelled)
        interaction.checkpoint()
        meter = self._build_assembler().create_power_meter(request.power_meter)
        sampler = PowerSampler(meter, request.parameters, wait=interaction.wait)
        sampler.validate_dummy_load_support()
        resistance = DummyLoadPreparation(request, request.dummy_load, sampler).calibrate(interaction)
        interaction.checkpoint()
        return DummyLoadCalibration(
            description=request.dummy_load.description,
            resistance=resistance,
            calibrated_at=utc_now(),
            power_meter_fingerprint=power_meter_fingerprint(request.power_meter),
        )

    def measure(self, request: MeasurementRequest, resistance: float | None = None) -> StandbyProbeResult:
        assembler = self._build_assembler()
        meter = assembler.create_power_meter(request.power_meter)
        sampler = PowerSampler(meter, request.parameters, wait=self._wait)
        if resistance is not None:
            sampler.set_dummy_load_resistance(resistance)
        runner = (
            assembler.create_runner(request, request.parameters, sampler)
            if isinstance(request, LightMeasurementRequest | SpeakerMeasurementRequest | FanMeasurementRequest)
            else None
        )
        try:
            if runner is not None:
                result = runner.measure_standby_power()
            else:
                # These devices have no automatic off control. The user confirms
                # they are in standby before starting this passive reading.
                start = time.time()
                self._wait(request.parameters.sleep_standby)
                result = sampler.take_measurement(start)
            power = result.power if result is not None else None
            if not is_valid_standby_power(power):
                return StandbyProbeResult(StandbyProbeStatus.UNAVAILABLE)
            return StandbyProbeResult(StandbyProbeStatus.MEASURED, power)
        except ZeroReadingError, OutdatedMeasurementError, MeasurementError:
            return StandbyProbeResult(StandbyProbeStatus.UNAVAILABLE)
        finally:
            if runner is not None:
                runner.cleanup()
