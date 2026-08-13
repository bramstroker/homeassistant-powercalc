from collections.abc import Iterable
from dataclasses import replace
from unittest.mock import MagicMock

from measure.assembler import MeasurementAssembler
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightInfo
from measure.controller.light.spec import HassLightControllerSpec
from measure.ha_app.light_probe import (
    LightLoadProbe,
    LightLoadProbeError,
    app_measurement_assembler,
    light_load_probe_label,
)
from measure.powermeter.powermeter import PowerMeasurementResult
from measure.powermeter.spec import HassPowerMeterSpec
from measure.request import LightMeasurementRequest
from measure.runner.light_plan import (
    ColorTempVariation,
    HsVariation,
    LightMeasurementPlan,
    LightModePlan,
    Variation,
    low_load_probe_variations,
)
from measure.tuning import MeasurementParameters
import pytest


class FakeLightController:
    def __init__(self, *, fail_cleanup: bool = False) -> None:
        self.changes: list[tuple[LutMode, bool, dict[str, object]]] = []
        self.closed = False
        self.fail_cleanup = fail_cleanup

    def change_light_state(self, lut_mode: LutMode, on: bool = True, **kwargs: object) -> None:
        if not on and self.fail_cleanup:
            raise RuntimeError("turn-off failed")
        self.changes.append((lut_mode, on, kwargs))

    def get_light_info(self) -> LightInfo:
        return LightInfo("test", min_mired=153, max_mired=454)

    def has_effect_support(self) -> bool:
        return True

    def get_effect_list(self) -> list[str]:
        return ["colorloop"]

    def close(self) -> None:
        self.closed = True
        if self.fail_cleanup:
            raise RuntimeError("close failed")


class FakePowerMeter:
    def __init__(self, powers: Iterable[float]) -> None:
        self._powers = iter(powers)
        self.calls = 0

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        del include_voltage
        self.calls += 1
        return PowerMeasurementResult(next(self._powers), 100, None)

    def has_voltage_support(self) -> bool:
        return False


class FakeAssembler:
    def __init__(self, controller: FakeLightController, meter: FakePowerMeter) -> None:
        self.controller = controller
        self.meter = meter

    def build_light_controller(self, _: object) -> FakeLightController:
        return self.controller

    def build_power_meter(self, _: object) -> FakePowerMeter:
        return self.meter


def request(
    *,
    parameters: MeasurementParameters | None = None,
    modes: set[LutMode] | None = None,
) -> LightMeasurementRequest:
    return LightMeasurementRequest(
        model_id="test",
        product_name="Test light",
        measure_device="Test meter",
        controller=HassLightControllerSpec(entity_id="light.test"),
        power_meter=HassPowerMeterSpec(entity_id="sensor.test_power"),
        modes=modes or {LutMode.HS},
        parameters=parameters or MeasurementParameters(sleep_time=0),
    )


def test_low_load_probe_variations_cover_static_mode_extremes_and_dedupe_hues() -> None:
    brightness = LightModePlan(LutMode.BRIGHTNESS, [Variation(5), Variation(1)])
    color_temp = LightModePlan(
        LutMode.COLOR_TEMP,
        [ColorTempVariation(1, 153), ColorTempVariation(1, 454), ColorTempVariation(10, 153)],
    )
    hs = LightModePlan(
        LutMode.HS,
        [HsVariation(1, 10000, 255), HsVariation(1, 30000, 255), HsVariation(1, 50000, 255)],
    )
    effects = LightModePlan(LutMode.EFFECT, [])

    assert low_load_probe_variations(LightMeasurementPlan([brightness, color_temp, hs, effects], [])) == [
        Variation(1),
        ColorTempVariation(1, 153),
        ColorTempVariation(1, 454),
        HsVariation(1, 10000, 255),
        HsVariation(1, 30000, 255),
        HsVariation(1, 50000, 255),
    ]


def test_active_probe_checks_rgb_primaries_and_caches_an_exact_request() -> None:
    controller = FakeLightController()
    meter = FakePowerMeter([1.2, 0.9, 1.1])
    assembler = FakeAssembler(controller, meter)
    probe = LightLoadProbe(lambda: assembler, wait=lambda _: None, now=lambda: 10)

    result = probe.evaluate(request())
    cached = probe.evaluate(request())

    assert result == cached
    assert result.checked_variations == 3
    assert result.minimum_aggregate_power_w == 0.9
    assert [point.label for point in result.points] == [
        "Color 0° / 100% saturation · brightness 1",
        "Color 120° / 100% saturation · brightness 1",
        "Color 240° / 100% saturation · brightness 1",
    ]
    assert meter.calls == 3
    hues = [change[2]["hue"] for change in controller.changes if change[0] == LutMode.HS]
    assert hues == [1, 21849, 43697]
    assert controller.changes[-1] == (LutMode.BRIGHTNESS, False, {})
    assert controller.closed


def test_active_probe_rejects_repeated_zero_on_saturated_green_and_cleans_up() -> None:
    controller = FakeLightController()
    meter = FakePowerMeter([1.2, 0, 0, 0, 0, 0, 0])
    assembler = FakeAssembler(controller, meter)
    probe = LightLoadProbe(lambda: assembler, wait=lambda _: None, now=lambda: 10)

    with pytest.raises(LightLoadProbeError, match="repeatedly returned 0 W") as error:
        probe.evaluate(request())

    assert error.value.help_url == "https://docs.powercalc.nl/contributing/measure/low-power-measurements/"
    assert error.value.help_label == "Low-power measurement guide"
    assert controller.changes[-1] == (LutMode.BRIGHTNESS, False, {})
    assert controller.closed
    assert meter.calls == 7


def test_active_probe_uses_configured_sample_count_and_request_key() -> None:
    controller = FakeLightController()
    meter = FakePowerMeter([1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7])
    assembler = FakeAssembler(controller, meter)
    probe = LightLoadProbe(lambda: assembler, wait=lambda _: None, now=lambda: 10)
    parameters = replace(MeasurementParameters(), sleep_time=0, sample_count=2, sleep_time_sample=0)

    first = probe.evaluate(request(parameters=parameters))
    second = probe.evaluate(request(parameters=replace(parameters, min_brightness=2)))

    assert first.minimum_aggregate_power_w == 1.5
    assert second.minimum_aggregate_power_w == 4.5
    assert meter.calls == 12


def test_active_probe_handles_effect_only_plan_and_formats_static_variations() -> None:
    controller = FakeLightController()
    assembler = FakeAssembler(controller, FakePowerMeter([]))
    probe = LightLoadProbe(lambda: assembler, wait=lambda _: None)

    result = probe.evaluate(request(modes={LutMode.EFFECT}))

    assert result.checked_variations == 0
    assert result.points == ()
    # Nothing was driven, so the light must be left exactly as the user had it.
    assert controller.changes == []
    assert controller.closed
    assert light_load_probe_label(Variation(1)) == "Brightness 1"
    assert light_load_probe_label(ColorTempVariation(1, 454)) == "Color temperature 454 mired · brightness 1"


def test_active_probe_wraps_controller_errors_and_cleanup_errors_do_not_mask_success() -> None:
    failing_assembler = MagicMock()
    failing_assembler.build_light_controller.side_effect = RuntimeError("controller unavailable")
    with pytest.raises(LightLoadProbeError, match="controller unavailable") as error:
        LightLoadProbe(lambda: failing_assembler).evaluate(request())

    # An adapter failure is not evidence of an unmeasurably low load.
    assert error.value.help_url is None

    controller = FakeLightController(fail_cleanup=True)
    meter = FakePowerMeter([1.2, 0.9, 1.1])
    result = LightLoadProbe(
        lambda: FakeAssembler(controller, meter),
        wait=lambda _: None,
        now=lambda: 10,
    ).evaluate(request())

    assert result.checked_variations == 3
    assert controller.closed


def test_app_measurement_assembler_builds_non_interactive_adapter_graph() -> None:
    assembler = app_measurement_assembler(home_assistant=MagicMock(), shelly_password="secret")  # noqa: S106

    assert isinstance(assembler, MeasurementAssembler)
