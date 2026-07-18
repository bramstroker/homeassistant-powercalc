from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from measure.home_assistant import HomeAssistantManager
from measure.powermeter.diagnostics import DiagnosticStatus, PowerMeterDiagnostics
from measure.powermeter.hass import HassPowerMeter
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter, PowerMeterDiagnosticSample
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec, ShellyPowerMeterSpec
import pytest


@dataclass
class FakeClock:
    current: float = 100.0

    def monotonic(self) -> float:
        return self.current

    def wait(self, seconds: float) -> None:
        self.current += seconds


class SampledPowerMeter(PowerMeter):
    def __init__(self, sample: Callable[[int], PowerMeterDiagnosticSample], *, supports_voltage: bool = False) -> None:
        self._sample = sample
        self._supports_voltage = supports_voltage
        self.calls = 0
        self.voltage_support_calls = 0

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        sample = self.diagnostic_sample()
        return PowerMeasurementResult(power=sample.power, updated=sample.reported_at)

    def has_voltage_support(self) -> bool:
        self.voltage_support_calls += 1
        return self._supports_voltage

    def diagnostic_sample(self) -> PowerMeterDiagnosticSample:
        sample = self._sample(self.calls)
        self.calls += 1
        return sample


def diagnose(
    sample: Callable[[int], PowerMeterDiagnosticSample],
    *,
    duration: float = 12,
    interval: float = 1,
) -> tuple[PowerMeterDiagnostics, SampledPowerMeter, HassPowerMeterSpec]:
    clock = FakeClock()
    meter = SampledPowerMeter(sample)
    diagnostics = PowerMeterDiagnostics(
        lambda _: meter,
        duration=duration,
        poll_interval=interval,
        cache_ttl=60,
        monotonic=clock.monotonic,
        wait=clock.wait,
    )
    return diagnostics, meter, HassPowerMeterSpec(entity_id="sensor.power")


def test_diagnostics_accepts_decimal_and_scientific_precision() -> None:
    diagnostics, _, spec = diagnose(
        lambda call: PowerMeterDiagnosticSample(power=0.1, raw_value="1e-1", reported_at=float(call)),
        duration=2,
    )

    result = diagnostics.evaluate(spec)

    assert result.precision_decimals == 1
    assert result.precision_status is DiagnosticStatus.GOOD


def test_diagnostics_warns_for_whole_watt_values() -> None:
    diagnostics, _, spec = diagnose(
        lambda call: PowerMeterDiagnosticSample(power=12, raw_value="12", reported_at=float(call)),
        duration=2,
    )

    result = diagnostics.evaluate(spec)

    assert result.success is True
    assert result.status is DiagnosticStatus.POOR
    assert result.precision_status is DiagnosticStatus.POOR
    assert any("0.1 W" in message for message in result.messages)


def test_diagnostics_grades_two_and_five_second_boundaries() -> None:
    good, _, good_spec = diagnose(
        lambda call: PowerMeterDiagnosticSample(power=1.2, raw_value="1.2", reported_at=float(call * 2)),
        duration=4,
    )
    warning, _, warning_spec = diagnose(
        lambda call: PowerMeterDiagnosticSample(power=1.2, raw_value="1.2", reported_at=float((call // 5) * 5)),
        duration=10,
    )

    good_result = good.evaluate(good_spec)
    warning_result = warning.evaluate(warning_spec)

    assert good_result.update_interval_status is DiagnosticStatus.GOOD
    assert good_result.max_report_interval_seconds == 2
    assert warning_result.update_interval_status is DiagnosticStatus.WARNING
    assert warning_result.max_report_interval_seconds == 5


def test_diagnostics_marks_slow_or_missing_reports_as_poor() -> None:
    slow, _, slow_spec = diagnose(
        lambda call: PowerMeterDiagnosticSample(power=1.2, raw_value="1.2", reported_at=float((call // 6) * 6)),
        duration=12,
    )
    missing, _, missing_spec = diagnose(
        lambda _: PowerMeterDiagnosticSample(power=1.2, raw_value="1.2", reported_at=10),
        duration=6,
    )

    slow_result = slow.evaluate(slow_spec)
    missing_result = missing.evaluate(missing_spec)

    assert slow_result.update_interval_status is DiagnosticStatus.POOR
    assert slow_result.max_report_interval_seconds == 6
    assert missing_result.update_interval_status is DiagnosticStatus.POOR
    assert missing_result.max_report_interval_seconds is None
    assert missing_result.reports_observed == 1


def test_diagnostics_includes_silence_after_the_last_report() -> None:
    diagnostics, _, spec = diagnose(
        lambda call: PowerMeterDiagnosticSample(
            power=1.2,
            raw_value="1.2",
            reported_at=float(min(call, 1)),
        ),
        duration=8,
    )

    result = diagnostics.evaluate(spec)

    assert result.update_interval_status is DiagnosticStatus.POOR
    assert result.max_report_interval_seconds == 7


def test_diagnostics_reuses_recent_result_unless_forced() -> None:
    diagnostics, meter, spec = diagnose(
        lambda call: PowerMeterDiagnosticSample(power=1.2, raw_value="1.2", reported_at=float(call)),
        duration=2,
    )

    first = diagnostics.evaluate(spec)
    second = diagnostics.evaluate(spec)
    forced = diagnostics.evaluate(spec, force=True)

    assert second is first
    assert forced is not first
    assert meter.calls == 6


@pytest.mark.parametrize(
    ("spec", "supports_voltage"),
    [
        (HassPowerMeterSpec(entity_id="sensor.power"), True),
        (ShellyPowerMeterSpec(device_ip="192.0.2.1"), False),
    ],
)
def test_diagnostics_report_voltage_capability_from_the_probed_meter(
    spec: HassPowerMeterSpec | ShellyPowerMeterSpec,
    supports_voltage: bool,
) -> None:
    meter = SampledPowerMeter(
        lambda _: PowerMeterDiagnosticSample(power=4.2, raw_value="4.2", reported_at=100),
        supports_voltage=supports_voltage,
    )
    diagnostics = PowerMeterDiagnostics(lambda _: meter, duration=0)

    result = diagnostics.evaluate(spec)

    assert result.supports_voltage is supports_voltage
    assert meter.voltage_support_calls == 1
    assert meter.calls == 1


def test_dummy_diagnostics_advertise_voltage_without_building_a_meter() -> None:
    builder = MagicMock()

    result = PowerMeterDiagnostics(builder).evaluate(DummyPowerMeterSpec())

    assert result.supports_voltage is True
    builder.assert_not_called()


def test_diagnostics_retain_known_voltage_capability_when_sampling_fails() -> None:
    def fail(_: int) -> PowerMeterDiagnosticSample:
        raise RuntimeError("Could not read power")

    meter = SampledPowerMeter(fail, supports_voltage=True)

    result = PowerMeterDiagnostics(lambda _: meter, duration=0).evaluate(
        ShellyPowerMeterSpec(device_ip="192.0.2.1"),
    )

    assert result.success is False
    assert result.supports_voltage is True


def test_diagnostics_leave_voltage_capability_unknown_when_building_fails() -> None:
    def fail(_: object) -> PowerMeter:
        raise RuntimeError("Could not connect")

    result = PowerMeterDiagnostics(fail).evaluate(ShellyPowerMeterSpec(device_ip="192.0.2.1"))

    assert result.success is False
    assert result.supports_voltage is None


def test_hass_diagnostic_sample_uses_raw_state_and_never_forces_an_update() -> None:
    reported = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
    home_assistant = MagicMock(spec=HomeAssistantManager)
    home_assistant.get_state.return_value = SimpleNamespace(
        state="12.30",
        last_reported=reported,
        last_updated=datetime(2026, 7, 15, 9, 59, tzinfo=UTC),
    )
    meter = HassPowerMeter(home_assistant, call_update_entity=True, entity_id="sensor.power")

    sample = meter.diagnostic_sample()

    assert sample.raw_value == "12.30"
    assert sample.reported_at == reported.timestamp()
    home_assistant.trigger_service.assert_not_called()


def test_direct_meter_reports_cadence_as_not_applicable() -> None:
    clock = FakeClock()
    meter = SampledPowerMeter(
        lambda _: PowerMeterDiagnosticSample(power=4.2, raw_value="4.2", reported_at=clock.current),
    )
    diagnostics = PowerMeterDiagnostics(
        lambda _: meter,
        monotonic=clock.monotonic,
        wait=clock.wait,
    )

    result = diagnostics.evaluate(ShellyPowerMeterSpec(device_ip="192.0.2.1"))

    assert result.status is DiagnosticStatus.GOOD
    assert result.precision_status is DiagnosticStatus.UNSUPPORTED
    assert result.precision_decimals is None
    assert result.update_interval_status is DiagnosticStatus.UNSUPPORTED
    assert result.max_report_interval_seconds is None
    assert meter.calls == 1


@pytest.mark.parametrize("raw_value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_readings_are_reported_as_connection_failures(raw_value: str) -> None:
    diagnostics, _, spec = diagnose(
        lambda call: PowerMeterDiagnosticSample(
            power=float(raw_value),
            raw_value=raw_value,
            reported_at=float(call),
        ),
        duration=0,
    )

    result = diagnostics.evaluate(spec)

    assert result.success is False
    assert result.message == "Power meter returned a non-finite reading"
