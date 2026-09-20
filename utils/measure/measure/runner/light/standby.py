from collections.abc import Callable
import time

from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController
from measure.powermeter.errors import OutdatedMeasurementError, ZeroReadingError
from measure.tuning import MeasurementParameters
from measure.utils.sampling import MeasurementError, MeasurementResult, PowerSampler


def measure_light_standby(
    controller: LightController,
    sampler: PowerSampler,
    parameters: MeasurementParameters,
    *,
    wait: Callable[[float], None],
    checkpoint: Callable[[], None],
    now: Callable[[], float] = time.time,
) -> MeasurementResult | None:
    """Measure the off-state load, recovering stale readings with bounded on/off nudges."""
    checkpoint()
    controller.change_light_state(LutMode.BRIGHTNESS, on=False)
    started = now()
    wait(parameters.sleep_standby)
    for attempt in range(parameters.max_nudges + 1):
        checkpoint()
        try:
            return sampler.take_measurement(start_timestamp=started)
        except ZeroReadingError, MeasurementError:
            # Too little load to read: a bare zero, or a dummy-load correction
            # that leaves nothing measurable. Nudging cannot recover either.
            return None
        except OutdatedMeasurementError:
            if attempt == parameters.max_nudges:
                return None
        controller.change_light_state(LutMode.BRIGHTNESS, on=True, bri=255)
        wait(parameters.pulse_time_nudge)
        checkpoint()
        controller.change_light_state(LutMode.BRIGHTNESS, on=False)
        started = now()
        wait(parameters.sleep_time_nudge)
    return None  # pragma: no cover - the final attempt returns or raises
