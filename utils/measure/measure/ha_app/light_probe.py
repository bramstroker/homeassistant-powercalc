from collections.abc import Callable
from dataclasses import asdict, dataclass
import json
import logging
from threading import RLock
import time

from measure.assembler import MeasurementAssembler
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController
from measure.execution import ImmediateInteraction
from measure.home_assistant import HomeAssistantManager
from measure.powermeter.errors import ZeroReadingError
from measure.request import LightMeasurementRequest
from measure.runner.light_plan import Variation, build_light_plan, low_load_probe_variations
from measure.runner.light_setup import set_light_to_maximum_brightness
from measure.util.measure_util import MeasureUtil

LIGHT_LOAD_PROBE_CACHE_SECONDS = 600
LOW_POWER_MEASUREMENT_GUIDE_URL = "https://docs.powercalc.nl/contributing/measure/low-power-measurements/"
_LOGGER = logging.getLogger("measure")


@dataclass(frozen=True)
class LightLoadProbePoint:
    label: str
    mode: LutMode
    power_w: float


@dataclass(frozen=True)
class LightLoadProbeResult:
    checked_variations: int
    minimum_aggregate_power_w: float
    points: tuple[LightLoadProbePoint, ...]


class LightLoadProbeError(Exception):
    """Raised when active preflight cannot verify the selected light's lowest loads.

    Only a genuine low-load failure carries documentation metadata; an adapter or
    connectivity failure must not be attributed to an unmeasurably low load.
    """

    def __init__(self, message: str, *, help_url: str | None = None, help_label: str | None = None) -> None:
        super().__init__(message)
        self.help_url = help_url
        self.help_label = help_label


class LightLoadProbe:
    """Drive representative low-load light points before a long measurement starts."""

    def __init__(
        self,
        build_assembler: Callable[[], MeasurementAssembler],
        *,
        wait: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._build_assembler = build_assembler
        self._wait = wait
        self._monotonic = monotonic
        self._now = now
        self._cache: dict[str, tuple[float, LightLoadProbeResult]] = {}
        self._lock = RLock()

    def evaluate(self, request: LightMeasurementRequest) -> LightLoadProbeResult:
        key = self._cache_key(request)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and self._monotonic() - cached[0] < LIGHT_LOAD_PROBE_CACHE_SECONDS:
                return cached[1]

        result = self._probe(request)
        with self._lock:
            self._cache[key] = (self._monotonic(), result)
        return result

    def _probe(self, request: LightMeasurementRequest) -> LightLoadProbeResult:
        assembler = self._build_assembler()
        controller: LightController | None = None
        light_driven = False
        try:
            controller = assembler.build_light_controller(request.controller)
            light_info = controller.get_light_info()
            effects = controller.get_effect_list() if LutMode.EFFECT in request.modes else []
            plan = build_light_plan(request.modes, request.parameters, light_info, effects)
            variations = low_load_probe_variations(plan)
            if not variations:
                return LightLoadProbeResult(checked_variations=0, minimum_aggregate_power_w=0, points=())

            meter = assembler.build_power_meter(request.power_meter)
            measure_util = MeasureUtil(meter, request.parameters, wait=self._wait)
            light_driven = True
            set_light_to_maximum_brightness(
                controller,
                light_info,
                variations[0].mode,
                sleep_time=request.parameters.sleep_time,
                wait=self._wait,
            )
            points = [
                LightLoadProbePoint(
                    label=light_load_probe_label(variation),
                    mode=variation.mode,
                    power_w=round(
                        self._measure_variation(
                            controller,
                            measure_util,
                            request,
                            variation,
                            initial=index == 0,
                        ),
                        3,
                    ),
                )
                for index, variation in enumerate(variations)
            ]
            return LightLoadProbeResult(
                checked_variations=len(points),
                minimum_aggregate_power_w=min(point.power_w for point in points),
                points=tuple(points),
            )
        except ZeroReadingError as error:
            raise LightLoadProbeError(
                "The power meter repeatedly returned 0 W while checking the selected light at its lowest-load "
                "settings. The measurement would likely fail later. Measure multiple identical lights together, "
                "use a suitable resistive dummy load, use a more sensitive meter, or increase Minimum brightness "
                "when that is acceptable for the profile.",
                help_url=LOW_POWER_MEASUREMENT_GUIDE_URL,
                help_label="Low-power measurement guide",
            ) from error
        except Exception as error:
            raise LightLoadProbeError(f"Could not complete the active light check: {error}") from error
        finally:
            if controller is not None:
                if light_driven:
                    try:
                        controller.change_light_state(LutMode.BRIGHTNESS, on=False)
                    except Exception as error:  # noqa: BLE001 - cleanup must not mask the probe result
                        _LOGGER.warning("Could not turn off the light after the active preflight check: %s", error)
                try:
                    controller.close()
                except Exception as error:  # noqa: BLE001 - cleanup must not mask the probe result
                    _LOGGER.warning("Could not close the light controller after the active preflight check: %s", error)

    def _measure_variation(
        self,
        controller: LightController,
        measure_util: MeasureUtil,
        request: LightMeasurementRequest,
        variation: Variation,
        *,
        initial: bool,
    ) -> float:
        start_timestamp = self._now()
        controller.change_light_state(variation.mode, on=True, **asdict(variation))
        self._wait(request.parameters.sleep_time)
        if initial:
            self._wait(request.parameters.sleep_initial)
        return measure_util.take_measurement(start_timestamp=start_timestamp).power

    @staticmethod
    def _cache_key(request: LightMeasurementRequest) -> str:
        value = request.model_dump(mode="json")
        value["modes"] = sorted(value["modes"])
        return json.dumps(value, sort_keys=True, separators=(",", ":"))


def app_measurement_assembler(
    *,
    home_assistant: HomeAssistantManager,
    shelly_password: str | None,
) -> MeasurementAssembler:
    """Build the non-interactive adapter graph used by an app preflight probe."""

    return MeasurementAssembler(
        ImmediateInteraction(),
        home_assistant=home_assistant,
        shelly_password=shelly_password,
    )


def light_load_probe_label(variation: Variation) -> str:
    """Describe a probe variation in native values for the preflight review."""

    values = asdict(variation)
    if variation.mode == LutMode.COLOR_TEMP:
        return f"Color temperature {values['ct']} mired · brightness {variation.bri}"
    if variation.mode == LutMode.HS:
        hue_degrees = round(int(values["hue"]) / 65535 * 360)
        saturation_percent = round(int(values["sat"]) / 255 * 100)
        return f"Color {hue_degrees}° / {saturation_percent}% saturation · brightness {variation.bri}"
    return f"Brightness {variation.bri}"
