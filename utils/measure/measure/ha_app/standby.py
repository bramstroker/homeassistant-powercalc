from collections.abc import Callable
import time

from measure.assembler import MeasurementAssembler
from measure.ha_app.light_probe import StandbyProbeResult, StandbyProbeStatus
from measure.powermeter.errors import OutdatedMeasurementError, ZeroReadingError
from measure.profile.standby import is_valid_standby_power
from measure.request import (
    FanMeasurementRequest,
    LightMeasurementRequest,
    MeasurementRequest,
    SpeakerMeasurementRequest,
)
from measure.utils.sampling import MeasurementError, PowerSampler


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
