from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from itertools import pairwise
import math
from threading import RLock
import time

from pydantic import BaseModel, ConfigDict, Field

from measure.powermeter.powermeter import PowerMeter, PowerMeterDiagnosticSample
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec, PowerMeterSpec


class DiagnosticStatus(StrEnum):
    GOOD = "good"
    WARNING = "warning"
    POOR = "poor"
    UNSUPPORTED = "unsupported"


class PowerMeterDiagnostic(BaseModel):
    """Connection and measurement-quality evidence collected before a run."""

    model_config = ConfigDict(frozen=True)

    success: bool
    power: float | None = None
    status: DiagnosticStatus
    precision_decimals: int | None = None
    max_report_interval_seconds: float | None = None
    reports_observed: int = 0
    duration_seconds: float = 0
    precision_status: DiagnosticStatus
    update_interval_status: DiagnosticStatus
    messages: list[str] = Field(default_factory=list)
    message: str | None = None


class PowerMeterDiagnostics:
    """Passively assess a configured power meter and briefly cache the result."""

    def __init__(
        self,
        build_power_meter: Callable[[PowerMeterSpec], PowerMeter],
        *,
        duration: float = 12,
        poll_interval: float = 0.5,
        cache_ttl: float = 60,
        monotonic: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        if duration < 0:
            raise ValueError("Diagnostic duration cannot be negative")
        if poll_interval <= 0:
            raise ValueError("Diagnostic poll interval must be positive")
        self._build_power_meter = build_power_meter
        self._duration = duration
        self._poll_interval = poll_interval
        self._cache_ttl = cache_ttl
        self._monotonic = monotonic
        self._wait = wait
        self._cache: dict[str, tuple[float, PowerMeterDiagnostic]] = {}
        self._lock = RLock()

    def evaluate(self, spec: PowerMeterSpec, *, force: bool = False) -> PowerMeterDiagnostic:
        """Return fresh diagnostics, or a recent equivalent result."""

        if isinstance(spec, DummyPowerMeterSpec):
            return PowerMeterDiagnostic(
                success=True,
                status=DiagnosticStatus.UNSUPPORTED,
                precision_status=DiagnosticStatus.UNSUPPORTED,
                update_interval_status=DiagnosticStatus.UNSUPPORTED,
                messages=["Synthetic dummy readings do not require measurement-device validation."],
            )

        cache_key = spec.model_dump_json()
        with self._lock:
            now = self._monotonic()
            cached = self._cache.get(cache_key)
            if not force and cached is not None and now - cached[0] <= self._cache_ttl:
                return cached[1]
            result = self._evaluate_uncached(spec)
            if result.success:
                self._cache[cache_key] = (self._monotonic(), result)
            return result

    def _evaluate_uncached(self, spec: PowerMeterSpec) -> PowerMeterDiagnostic:
        started = self._monotonic()
        samples: list[_ObservedSample] = []
        try:
            meter = self._build_power_meter(spec)
            samples.append(_ObservedSample(meter.diagnostic_sample(), self._monotonic() - started))
            if not isinstance(spec, HassPowerMeterSpec):
                return _summarize_direct(samples[0], duration=round(self._monotonic() - started, 1))
            deadline = started + self._duration
            while (remaining := deadline - self._monotonic()) > 0:
                self._wait(min(self._poll_interval, remaining))
                samples.append(_ObservedSample(meter.diagnostic_sample(), self._monotonic() - started))
            return _summarize(samples, duration=round(self._monotonic() - started, 1))
        except Exception as error:  # noqa: BLE001 - diagnostics must surface adapter and parsing failures
            message = str(error) or "Could not read from the power meter"
            return PowerMeterDiagnostic(
                success=False,
                status=DiagnosticStatus.POOR,
                precision_status=DiagnosticStatus.UNSUPPORTED,
                update_interval_status=DiagnosticStatus.UNSUPPORTED,
                duration_seconds=round(self._monotonic() - started, 1),
                messages=[message],
                message=message,
            )


@dataclass(frozen=True)
class _ObservedSample:
    sample: PowerMeterDiagnosticSample
    observed_after: float


def _summarize_direct(observation: _ObservedSample, *, duration: float) -> PowerMeterDiagnostic:
    if not math.isfinite(observation.sample.power):
        raise ValueError("Power meter returned a non-finite reading")
    return PowerMeterDiagnostic(
        success=True,
        power=observation.sample.power,
        status=DiagnosticStatus.GOOD,
        reports_observed=1,
        duration_seconds=duration,
        precision_status=DiagnosticStatus.UNSUPPORTED,
        update_interval_status=DiagnosticStatus.UNSUPPORTED,
        messages=["Resolution and update frequency are not applicable because Powercalc polls this meter directly."],
    )


def _summarize(samples: list[_ObservedSample], *, duration: float) -> PowerMeterDiagnostic:
    precision = min(_decimal_places(observation.sample.raw_value) for observation in samples)
    precision_status = DiagnosticStatus.GOOD if precision >= 1 else DiagnosticStatus.POOR
    update_status, max_interval, reports_observed = _report_cadence(samples, duration)
    messages = _diagnostic_messages(precision_status, update_status, max_interval)
    status = DiagnosticStatus.GOOD
    if DiagnosticStatus.POOR in {precision_status, update_status}:
        status = DiagnosticStatus.POOR
    elif DiagnosticStatus.WARNING in {precision_status, update_status}:
        status = DiagnosticStatus.WARNING
    return PowerMeterDiagnostic(
        success=True,
        power=samples[-1].sample.power,
        status=status,
        precision_decimals=precision,
        max_report_interval_seconds=round(max_interval, 2) if max_interval is not None else None,
        reports_observed=reports_observed,
        duration_seconds=duration,
        precision_status=precision_status,
        update_interval_status=update_status,
        messages=messages,
    )


def _report_cadence(
    samples: list[_ObservedSample],
    duration: float,
) -> tuple[DiagnosticStatus, float | None, int]:
    reports: list[_ObservedSample] = []
    for observation in samples:
        if not reports or observation.sample.reported_at != reports[-1].sample.reported_at:
            reports.append(observation)
    report_times = [observation.sample.reported_at for observation in reports]
    intervals = [later - earlier for earlier, later in pairwise(report_times) if later >= earlier]
    if intervals:
        intervals.append(max(0, duration - reports[-1].observed_after))
    max_interval = max(intervals) if intervals else None
    if max_interval is None:
        update_status = DiagnosticStatus.POOR
    elif max_interval <= 2:
        update_status = DiagnosticStatus.GOOD
    elif max_interval <= 5:
        update_status = DiagnosticStatus.WARNING
    else:
        update_status = DiagnosticStatus.POOR
    return update_status, max_interval, len(report_times)


def _diagnostic_messages(
    precision_status: DiagnosticStatus,
    update_status: DiagnosticStatus,
    max_interval: float | None,
) -> list[str]:
    messages: list[str] = []
    if precision_status is DiagnosticStatus.POOR:
        messages.append("Power meter does not consistently report 0.1 W resolution or better.")
    if update_status is DiagnosticStatus.WARNING:
        assert max_interval is not None
        messages.append(f"Power meter updates every {max_interval:.1f} s; 2 s or faster is recommended.")
    elif update_status is DiagnosticStatus.POOR:
        if max_interval is None:
            messages.append(
                "Power meter did not report often enough during the validation window; 5 s or faster is required.",
            )
        else:
            messages.append(f"Power meter took up to {max_interval:.1f} s to update; 5 s or faster is required.")
    return messages


def _decimal_places(raw_value: str) -> int:
    try:
        value = Decimal(raw_value)
    except InvalidOperation:
        return 0
    if not value.is_finite():
        raise ValueError("Power meter returned a non-finite reading")
    exponent = value.as_tuple().exponent
    return max(0, -int(exponent))
