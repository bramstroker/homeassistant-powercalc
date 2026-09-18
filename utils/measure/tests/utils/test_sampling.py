from dataclasses import dataclass
import logging
import time
from typing import Any
from unittest.mock import MagicMock, patch

from measure.cancellation import MeasurementCancelledError
from measure.const import RETRY_COUNT_LIMIT, Trend
from measure.powermeter.errors import ApiConnectionError, UnsupportedFeatureError, ZeroReadingError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
from measure.tuning import MeasurementParameters
from measure.utils.sampling import (
    AverageMeasurementConvergence,
    AverageMeasurementSnapshot,
    AverageMeasurementState,
    DummyLoadMeasurementError,
    MeasurementResult,
    NoValidReadingsError,
    PowerSampler,
)
import pytest

from tests.conftest import MockConfigFactory


@dataclass
class SamplingClock:
    elapsed: float = 0.0

    def wait(self, seconds: float) -> None:
        self.elapsed += seconds


@pytest.mark.parametrize("measure_resistance", [False, True])
def test_average_skips_zero_readings_and_stops_before_deadline(measure_resistance: bool) -> None:
    clock = SamplingClock()
    meter = MagicMock(spec=PowerMeter)
    meter.get_power.side_effect = [
        PowerMeasurementResult(power=0.004, voltage=10, updated=0),
        PowerMeasurementResult(power=4, voltage=10, updated=0),
        PowerMeasurementResult(power=8, voltage=10, updated=0),
    ]
    sampler = PowerSampler(meter, MeasurementParameters(sleep_time=2), wait=clock.wait)
    progress = MagicMock()

    with patch("measure.utils.sampling.time.time", side_effect=lambda: clock.elapsed):
        result = sampler.take_average_measurement(6, measure_resistance=measure_resistance, on_progress=progress)

    assert result == MeasurementResult(power=18.75 if measure_resistance else 6, voltages=[10, 10])
    assert meter.get_power.call_count == 3
    assert clock.elapsed == 4
    progress.assert_called_with(6, 6)


def test_average_stops_when_measurements_converge() -> None:
    clock = SamplingClock()
    meter = MagicMock(spec=PowerMeter)
    meter.get_power.return_value = PowerMeasurementResult(power=8, updated=0)
    sampler = PowerSampler(meter, MeasurementParameters(sleep_time=2), wait=clock.wait)
    convergence = AverageMeasurementConvergence(
        min_duration=4, window_duration=2, absolute_threshold=0.1, relative_threshold=0.01
    )

    with patch("measure.utils.sampling.time.time", side_effect=lambda: clock.elapsed):
        result = sampler.take_average_measurement(60, convergence=convergence)

    assert result == MeasurementResult(power=8, voltages=[])
    assert clock.elapsed == 4
    assert meter.get_power.call_count == 3


@pytest.mark.parametrize(
    "snapshots, expected",
    [
        ([AverageMeasurementSnapshot(0, 10), AverageMeasurementSnapshot(3, 10)], False),
        ([AverageMeasurementSnapshot(4, 10)], False),
        ([AverageMeasurementSnapshot(3, 10), AverageMeasurementSnapshot(4, 10)], False),
        ([AverageMeasurementSnapshot(0, 0), AverageMeasurementSnapshot(4, 1)], False),
        ([AverageMeasurementSnapshot(0, 0), AverageMeasurementSnapshot(4, 0)], True),
        ([AverageMeasurementSnapshot(0, 10), AverageMeasurementSnapshot(4, 10.125)], True),
        ([AverageMeasurementSnapshot(0, 100), AverageMeasurementSnapshot(4, 101)], True),
        ([AverageMeasurementSnapshot(0, 100), AverageMeasurementSnapshot(4, 102)], False),
        # Compare with the newest snapshot old enough to span the lookback window.
        (
            [AverageMeasurementSnapshot(0, 2), AverageMeasurementSnapshot(2, 10), AverageMeasurementSnapshot(4, 10)],
            True,
        ),
    ],
)
def test_average_convergence_requires_enough_history_and_stable_power(
    snapshots: list[AverageMeasurementSnapshot],
    expected: bool,
) -> None:
    convergence = AverageMeasurementConvergence(
        min_duration=4, window_duration=2, absolute_threshold=0.125, relative_threshold=0.01
    )

    assert PowerSampler.has_average_converged(snapshots, convergence) is expected


@pytest.mark.parametrize("measure_resistance", [False, True])
def test_average_with_only_zero_readings_fails(measure_resistance: bool) -> None:
    clock = SamplingClock()
    meter = MagicMock(spec=PowerMeter)
    meter.get_power.return_value = PowerMeasurementResult(power=0, voltage=230, updated=0)
    sampler = PowerSampler(meter, MeasurementParameters(sleep_time=2), wait=clock.wait)

    with (
        patch("measure.utils.sampling.time.time", side_effect=lambda: clock.elapsed),
        pytest.raises(NoValidReadingsError),
    ):
        sampler.take_average_measurement(4, measure_resistance=measure_resistance)

    assert meter.get_power.call_count == 2


@pytest.mark.parametrize("voltage", [None, 0, 0.5])
@pytest.mark.parametrize("measure_resistance", [False, True])
def test_dummy_load_measurements_require_valid_voltage(voltage: float | None, measure_resistance: bool) -> None:
    meter = MagicMock(spec=PowerMeter)
    meter.has_voltage_support.return_value = True
    meter.get_power.return_value = PowerMeasurementResult(power=5, voltage=voltage, updated=0)
    sampler = PowerSampler(meter, MeasurementParameters(max_retries=0))

    if measure_resistance:
        with pytest.raises(ZeroReadingError):
            sampler.take_average_measurement(1, measure_resistance=True)
    else:
        sampler.set_dummy_load_resistance(10)
        with pytest.raises(ZeroReadingError):
            sampler.take_measurement()

    meter.get_power.assert_called_once_with(include_voltage=True)


@pytest.mark.parametrize("resistance", [0, -10])
def test_invalid_dummy_load_resistance_preserves_previous_calibration(resistance: float) -> None:
    meter = MagicMock(spec=PowerMeter)
    meter.has_voltage_support.return_value = True
    sampler = PowerSampler(meter, MeasurementParameters())
    sampler.set_dummy_load_resistance(10)

    with pytest.raises(DummyLoadMeasurementError, match="must be positive"):
        sampler.set_dummy_load_resistance(resistance)

    assert sampler.dummy_load_value == 10


def test_empty_sample_batch_fails_without_reading_meter() -> None:
    meter = MagicMock(spec=PowerMeter)
    sampler = PowerSampler(meter, MeasurementParameters(sample_count=0))

    with pytest.raises(NoValidReadingsError):
        sampler.take_measurement()

    meter.get_power.assert_not_called()


def test_retry_safety_limit_caps_excessive_configuration() -> None:
    meter = MagicMock(spec=PowerMeter)
    error = ApiConnectionError("Disconnected")
    meter.get_power.side_effect = error
    wait = MagicMock()
    sampler = PowerSampler(meter, MeasurementParameters(max_retries=RETRY_COUNT_LIMIT + 10), wait=wait)

    with pytest.raises(ApiConnectionError) as raised:
        sampler.take_measurement()

    assert raised.value is error
    assert meter.get_power.call_count == RETRY_COUNT_LIMIT + 1
    assert wait.call_count == RETRY_COUNT_LIMIT


@pytest.mark.parametrize("power", [0, -1, 0.004])
def test_point_measurement_rejects_non_positive_power(power: float) -> None:
    meter = MagicMock(spec=PowerMeter)
    meter.get_power.return_value = PowerMeasurementResult(power=power, updated=0)
    sampler = PowerSampler(meter, MeasurementParameters(max_retries=0))

    with pytest.raises(ZeroReadingError):
        sampler.take_measurement()

    meter.get_power.assert_called_once_with(include_voltage=False)


@pytest.mark.parametrize("measure_resistance", [False, True])
def test_failed_live_feedback_does_not_discard_measurements(measure_resistance: bool) -> None:
    clock = SamplingClock()
    meter = MagicMock(spec=PowerMeter)
    meter.get_power.return_value = PowerMeasurementResult(power=5, voltage=10, updated=0)
    callback = MagicMock(side_effect=RuntimeError("Disconnected listener"))
    sampler = PowerSampler(
        meter,
        MeasurementParameters(sleep_time=2),
        wait=clock.wait,
        on_sample=callback,
        on_calibration_sample=callback,
    )

    with patch("measure.utils.sampling.time.time", side_effect=lambda: clock.elapsed):
        result = sampler.take_average_measurement(1, measure_resistance=measure_resistance)

    assert result == MeasurementResult(power=20 if measure_resistance else 5, voltages=[10])
    callback.assert_called_once()


@pytest.mark.parametrize(
    "values, expected",
    [
        ([1.0, 2.0, 3.0], 1.0),
        ([3.0, 2.0, 1.0], -1.0),
        ([4.0], 0.0),
    ],
)
def test_linear_slope_does_not_require_numpy(values: list[float], expected: float) -> None:
    assert PowerSampler._calculate_linear_slope(values) == pytest.approx(expected)  # noqa: SLF001


@pytest.mark.parametrize(
    "averages, expected",
    [
        # Sub-threshold drift on a high-ohm load (0.5 Ω/sample on ~6.2 kΩ) is meter noise, not a trend
        ([6226.0 + 0.5 * index for index in range(20)], Trend.STEADY),
        # Real warm-up drift still registers regardless of resistance magnitude
        ([6000.0 + 10.0 * index for index in range(20)], Trend.INCREASING),
        ([6000.0 - 10.0 * index for index in range(20)], Trend.DECREASING),
        # The relative threshold keeps its sensitivity on low-ohm loads such as incandescent bulbs
        ([40.0 + 0.05 * index for index in range(20)], Trend.INCREASING),
        # Drift in only one half still means the load has not settled
        ([6000.0 + 10.0 * index for index in range(10)] + [6100.0] * 10, Trend.INCREASING),
        ([6100.0] * 10 + [6100.0 - 10.0 * index for index in range(10)], Trend.DECREASING),
    ],
)
def test_dummy_load_trend_uses_relative_threshold(averages: list[float], expected: Trend) -> None:
    assert PowerSampler.classify_dummy_load_trend(averages) == expected


def test_dummy_load_trend_requires_twenty_samples() -> None:
    assert PowerSampler.classify_dummy_load_trend([6226.0] * 19) is None


def test_dummy_load_trend_rejects_opposing_drift_as_unstable() -> None:
    averages = [6000.0 + 10.0 * index for index in range(10)] + [6100.0 - 10.0 * index for index in range(10)]

    assert PowerSampler.classify_dummy_load_trend(averages) is Trend.UNSTABLE


def test_no_valid_average_readings_raise_typed_error(mock_config_factory: MockConfigFactory) -> None:
    sampler = PowerSampler(MagicMock(PowerMeter), mock_config_factory())
    empty = AverageMeasurementState(start_time=0, readings=[], snapshots=[], voltages=[])

    with (
        patch.object(sampler, "_collect_average_measurements", return_value=empty),
        pytest.raises(NoValidReadingsError),
    ):
        sampler.take_average_measurement(1)


@pytest.mark.parametrize("interrupt", [MeasurementCancelledError, KeyboardInterrupt])
@pytest.mark.parametrize("finish_on_interrupt", [False, True])
def test_average_stop_preserves_samples_only_when_requested(
    mock_config_factory: MockConfigFactory,
    interrupt: type[BaseException],
    finish_on_interrupt: bool,
) -> None:
    clock = [0.0]
    meter = MagicMock(PowerMeter)
    meter.get_power.side_effect = [
        PowerMeasurementResult(power=4.0, voltage=230.0, updated=0),
        PowerMeasurementResult(power=8.0, voltage=232.0, updated=0),
    ]

    def wait(seconds: float) -> None:
        clock[0] += seconds
        if meter.get_power.call_count == 2:
            raise interrupt

    progress = MagicMock()
    util = PowerSampler(meter, mock_config_factory({"sleep_time": 2}), include_voltage=lambda: True, wait=wait)
    with patch("time.time", side_effect=lambda: clock[0]):
        if not finish_on_interrupt:
            with pytest.raises(interrupt):
                util.take_average_measurement(60, on_progress=progress)
        else:
            result = util.take_average_measurement(60, on_progress=progress, finish_on_interrupt=True)
            assert result == MeasurementResult(power=6.0, voltages=[230.0, 232.0])
            progress.assert_called_with(4.0, 60)


@pytest.mark.parametrize("interrupt", [MeasurementCancelledError, KeyboardInterrupt])
def test_average_stop_without_readings_is_not_successful(
    mock_config_factory: MockConfigFactory,
    interrupt: type[BaseException],
) -> None:
    meter = MagicMock(PowerMeter)
    meter.get_power.side_effect = interrupt
    util = PowerSampler(meter, mock_config_factory())
    with pytest.raises(interrupt):
        util.take_average_measurement(60, finish_on_interrupt=True)


def test_dummy_load_requires_voltage_support(mock_config_factory: MockConfigFactory) -> None:
    power_meter = MagicMock(PowerMeter)
    power_meter.has_voltage_support.return_value = False
    sampler = PowerSampler(power_meter, mock_config_factory())

    with pytest.raises(UnsupportedFeatureError):
        sampler.set_dummy_load_resistance(42.5)


def test_resistance_reading_emits_live_calibration_values(mock_config_factory: MockConfigFactory) -> None:
    power_meter = MagicMock(PowerMeter)
    power_meter.get_power.return_value = PowerMeasurementResult(power=60.0, voltage=230.0, updated=time.time())
    samples: list[tuple[float, float, float]] = []
    sampler = PowerSampler(
        power_meter,
        mock_config_factory(),
        on_calibration_sample=lambda power, resistance, voltage: samples.append((power, resistance, voltage)),
    )

    result = sampler._take_resistance_reading()  # noqa: SLF001

    assert result == MeasurementResult(power=pytest.approx(881.6667), voltages=[230.0])
    assert samples == [(60.0, pytest.approx(881.6667), 230.0)]


def test_dummy_load_emits_corrected_sample(mock_config_factory: MockConfigFactory) -> None:
    power_meter = MagicMock(PowerMeter)
    power_meter.has_voltage_support.return_value = True
    power_meter.get_power.return_value = PowerMeasurementResult(power=20.0, voltage=10.0, updated=time.time())
    samples: list[float] = []
    sampler = PowerSampler(power_meter, mock_config_factory(), on_sample=samples.append)
    sampler.set_dummy_load_resistance(10.0)

    result = sampler.take_measurement()

    assert result.power == pytest.approx(10.0)
    assert samples
    assert all(sample == pytest.approx(10.0) for sample in samples)


@patch("time.time")
def test_average_measurement_uses_dummy_load_correction_pipeline(
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
) -> None:
    power_meter = MagicMock(PowerMeter)
    power_meter.has_voltage_support.return_value = True
    power_meter.get_power.return_value = PowerMeasurementResult(power=20.0, voltage=10.0, updated=0.0)
    samples: list[float] = []
    sampler = PowerSampler(power_meter, mock_config_factory(), on_sample=samples.append)
    sampler.set_dummy_load_resistance(10.0)
    mock_time.side_effect = lambda: 100.0 if power_meter.get_power.call_count else 0.0

    result = sampler.take_average_measurement(duration=10)

    assert result == MeasurementResult(power=10.0, voltages=[10.0])
    assert samples == [10.0]
    power_meter.get_power.assert_called_once_with(include_voltage=True)


def test_measurement_retries_outdated_reading_without_emitting_it(mock_config_factory: MockConfigFactory) -> None:
    power_meter = MagicMock(PowerMeter)
    power_meter.get_power.side_effect = [
        PowerMeasurementResult(power=5.0, updated=10.0),
        PowerMeasurementResult(power=7.0, updated=30.0),
    ]
    samples: list[float] = []
    sampler = PowerSampler(
        power_meter,
        mock_config_factory({"max_retries": 1, "sample_count": 1}),
        wait=lambda _: None,
        on_sample=samples.append,
    )

    result = sampler.take_measurement(start_timestamp=20.0)

    assert result == MeasurementResult(power=7.0, voltages=[])
    assert samples == [7.0]
    assert power_meter.get_power.call_count == 2


def test_dummy_load_rejects_non_positive_corrected_power(mock_config_factory: MockConfigFactory) -> None:
    power_meter = MagicMock(PowerMeter)
    power_meter.has_voltage_support.return_value = True
    power_meter.get_power.return_value = PowerMeasurementResult(power=10.0, voltage=10.0, updated=time.time())
    sampler = PowerSampler(power_meter, mock_config_factory())
    sampler.set_dummy_load_resistance(10.0)

    with pytest.raises(DummyLoadMeasurementError, match="non-positive target power"):
        sampler.take_measurement()


class _ErrorThenSuccessPowerMeter(PowerMeter):
    """Power meter that raises errors for the first N calls, then succeeds."""

    def __init__(self, error_count: int, success_power: float = 5.0) -> None:
        self._error_count = error_count
        self._success_power = success_power
        self._call_count = 0

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        self._call_count += 1
        if self._call_count <= self._error_count:
            raise ApiConnectionError(f"Connection timeout (call {self._call_count})")
        return PowerMeasurementResult(power=self._success_power, updated=time.time())

    def has_voltage_support(self) -> bool:
        return False

    def process_answers(self, answers: dict[str, Any]) -> None:
        """No-op: not needed for test power meters."""

    @property
    def call_count(self) -> int:
        return self._call_count


class _AlwaysFailPowerMeter(PowerMeter):
    """Power meter that always raises ApiConnectionError."""

    def __init__(self) -> None:
        self._call_count = 0

    def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
        self._call_count += 1
        raise ApiConnectionError(f"Connection timeout (call {self._call_count})")

    def has_voltage_support(self) -> bool:
        return False

    def process_answers(self, answers: dict[str, Any]) -> None:
        """No-op: not needed for test power meters."""

    @property
    def call_count(self) -> int:
        return self._call_count


@patch("time.time")
def test_average_measurement_retries_on_transient_error(
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A single transient error should be retried and the measurement should complete."""
    caplog.set_level(logging.WARNING)
    mock_config = mock_config_factory(config_values={"max_retries": 3})
    power_meter = _ErrorThenSuccessPowerMeter(error_count=1, success_power=5.0)
    sampler = PowerSampler(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count > 1 else 0.0

    result = sampler.take_average_measurement(duration=10)

    assert result.power > 0
    assert power_meter.call_count == 2
    assert "Error during average measurement (attempt 1/3)" in caplog.text


@patch("time.time")
def test_average_measurement_retries_multiple_consecutive_errors(
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
) -> None:
    """Multiple consecutive errors within max_retries should be tolerated."""
    mock_config = mock_config_factory(config_values={"max_retries": 3})
    power_meter = _ErrorThenSuccessPowerMeter(error_count=3, success_power=4.0)
    sampler = PowerSampler(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count > 3 else 0.0

    result = sampler.take_average_measurement(duration=10)

    assert result.power == 4.0
    assert power_meter.call_count == 4


@patch("time.time", return_value=0.0)
def test_average_measurement_raises_after_max_retries_exceeded(
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
) -> None:
    """Consecutive errors exceeding max_retries should re-raise the error."""
    mock_config = mock_config_factory(config_values={"max_retries": 2})
    power_meter = _AlwaysFailPowerMeter()
    sampler = PowerSampler(power_meter, mock_config)

    with pytest.raises(ApiConnectionError):
        sampler.take_average_measurement(duration=10)

    # Should have been called max_retries + 1 times (initial + retries)
    assert power_meter.call_count == 3


@patch("time.time")
def test_average_measurement_resets_error_count_on_success(
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
) -> None:
    """After a successful reading, the consecutive error counter should reset."""
    mock_config = mock_config_factory(config_values={"max_retries": 2})

    call_count = 0

    class _IntermittentPowerMeter(PowerMeter):
        """Fails once, succeeds once, fails once, succeeds — never exceeds max_retries consecutively."""

        def get_power(self, include_voltage: bool = False) -> PowerMeasurementResult:
            nonlocal call_count
            call_count += 1
            # Fail on calls 1 and 3, succeed on calls 2, 4, 5, ...
            if call_count in (1, 3):
                raise ApiConnectionError(f"Timeout (call {call_count})")
            return PowerMeasurementResult(power=3.0, updated=time.time())

        def has_voltage_support(self) -> bool:
            return False

        def process_answers(self, answers: dict[str, Any]) -> None:
            """No-op: not needed for test power meters."""

    power_meter = _IntermittentPowerMeter()
    sampler = PowerSampler(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if call_count >= 4 else 0.0

    result = sampler.take_average_measurement(duration=10)

    assert result.power == 3.0
    assert call_count == 4


@patch("time.time")
def test_average_measurement_excludes_failed_readings_from_average(
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
) -> None:
    """The average should only include successful readings, not be affected by errors."""
    mock_config = mock_config_factory(config_values={"max_retries": 3})
    # First call fails, subsequent calls return exactly 7.0
    power_meter = _ErrorThenSuccessPowerMeter(error_count=1, success_power=7.0)
    sampler = PowerSampler(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count >= 3 else 0.0

    result = sampler.take_average_measurement(duration=10)

    # Average should be exactly 7.0 since all successful readings are 7.0
    assert result.power == 7.0
