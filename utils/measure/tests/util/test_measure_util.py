from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

from measure.powermeter.errors import ApiConnectionError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
from measure.util.measure_util import MeasureUtil
import pytest

from tests.conftest import MockConfigFactory


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
@patch("time.sleep", return_value=None)
def test_average_measurement_retries_on_transient_error(
    mock_sleep: MagicMock,
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
) -> None:
    """A single transient error should be retried and the measurement should complete."""
    mock_config = mock_config_factory(config_values={"max_retries": 3})
    power_meter = _ErrorThenSuccessPowerMeter(error_count=1, success_power=5.0)
    measure_util = MeasureUtil(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count > 1 else 0.0

    result = measure_util.take_average_measurement(duration=10)

    assert result.power > 0
    assert power_meter.call_count == 2


@patch("time.time")
@patch("time.sleep", return_value=None)
def test_average_measurement_retries_multiple_consecutive_errors(
    mock_sleep: MagicMock,
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
) -> None:
    """Multiple consecutive errors within max_retries should be tolerated."""
    mock_config = mock_config_factory(config_values={"max_retries": 3})
    power_meter = _ErrorThenSuccessPowerMeter(error_count=3, success_power=4.0)
    measure_util = MeasureUtil(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count > 3 else 0.0

    result = measure_util.take_average_measurement(duration=10)

    assert result.power == 4.0
    assert power_meter.call_count == 4


@patch("time.time", return_value=0.0)
@patch("time.sleep", return_value=None)
def test_average_measurement_raises_after_max_retries_exceeded(
    mock_sleep: MagicMock,
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
) -> None:
    """Consecutive errors exceeding max_retries should re-raise the error."""
    mock_config = mock_config_factory(config_values={"max_retries": 2})
    power_meter = _AlwaysFailPowerMeter()
    measure_util = MeasureUtil(power_meter, mock_config)

    with pytest.raises(ApiConnectionError):
        measure_util.take_average_measurement(duration=10)

    # Should have been called max_retries + 1 times (initial + retries)
    assert power_meter.call_count == 3


@patch("time.time")
@patch("time.sleep", return_value=None)
def test_average_measurement_resets_error_count_on_success(
    mock_sleep: MagicMock,
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
    measure_util = MeasureUtil(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if call_count >= 4 else 0.0

    result = measure_util.take_average_measurement(duration=10)

    assert result.power == 3.0
    assert call_count == 4


@patch("time.time")
@patch("time.sleep", return_value=None)
def test_average_measurement_logs_warnings_on_retry(
    mock_sleep: MagicMock,
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Transient errors should be logged as warnings, not errors."""
    import logging

    caplog.set_level(logging.WARNING)
    mock_config = mock_config_factory(config_values={"max_retries": 3})
    power_meter = _ErrorThenSuccessPowerMeter(error_count=2, success_power=5.0)
    measure_util = MeasureUtil(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count > 2 else 0.0

    result = measure_util.take_average_measurement(duration=10)

    assert result.power > 0
    assert "Connection error while taking reading (retry 1/3)" in caplog.text
    assert "Connection error while taking reading (retry 2/3)" in caplog.text


@patch("time.time")
@patch("time.sleep", return_value=None)
def test_average_measurement_excludes_failed_readings_from_average(
    mock_sleep: MagicMock,
    mock_time: MagicMock,
    mock_config_factory: MockConfigFactory,
) -> None:
    """The average should only include successful readings, not be affected by errors."""
    mock_config = mock_config_factory(config_values={"max_retries": 3})
    # First call fails, subsequent calls return exactly 7.0
    power_meter = _ErrorThenSuccessPowerMeter(error_count=1, success_power=7.0)
    measure_util = MeasureUtil(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count >= 3 else 0.0

    result = measure_util.take_average_measurement(duration=10)

    # Average should be exactly 7.0 since all successful readings are 7.0
    assert result.power == 7.0
