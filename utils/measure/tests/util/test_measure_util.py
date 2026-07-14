from __future__ import annotations

import ast
import logging
from pathlib import Path
import time
from typing import Any
from unittest.mock import MagicMock, patch

from measure.powermeter.errors import ApiConnectionError, UnsupportedFeatureError
from measure.powermeter.powermeter import PowerMeasurementResult, PowerMeter
import measure.util.measure_util as measure_util_module
from measure.util.measure_util import AverageMeasurementState, MeasureUtil, NoValidReadingsError
import pytest

from tests.conftest import MockConfigFactory


class _RecordingInteraction:
    def __init__(self, choice: bool = False) -> None:
        self.choice = choice
        self.notifications: list[str] = []

    def confirm(self, message: str) -> None:
        raise AssertionError(f"Unexpected confirmation: {message}")

    def choose(self, message: str, *, default: bool) -> bool:
        self.notifications.append(message)
        return self.choice

    def notify(self, message: str) -> None:
        self.notifications.append(message)


def test_shared_measure_util_has_no_process_or_console_calls() -> None:
    source_path = Path(str(measure_util_module.__file__))
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"exit", "input", "print"}
    }
    raises_system_exit = any(
        isinstance(node, ast.Raise) and isinstance(node.exc, ast.Name) and node.exc.id == "SystemExit"
        for node in ast.walk(tree)
    )

    assert forbidden == set()
    assert not raises_system_exit


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([1.0, 2.0, 3.0], 1.0),
        ([3.0, 2.0, 1.0], -1.0),
        ([4.0], 0.0),
    ],
)
def test_linear_slope_does_not_require_numpy(values: list[float], expected: float) -> None:
    assert MeasureUtil._linear_slope(values) == pytest.approx(expected)  # noqa: SLF001


def test_no_valid_average_readings_raise_typed_error(mock_config_factory: MockConfigFactory) -> None:
    measure_util = MeasureUtil(MagicMock(PowerMeter), mock_config_factory())
    empty = AverageMeasurementState(start_time=0, readings=[], snapshots=[], voltages=[])

    with (
        patch.object(measure_util, "_collect_average_measurements", return_value=empty),
        pytest.raises(NoValidReadingsError),
    ):
        measure_util.take_average_measurement(1)


def test_dummy_load_reuses_value_through_interaction_boundary(
    tmp_path: Path,
    mock_config_factory: MockConfigFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistent = tmp_path / ".persistent"
    persistent.mkdir()
    (persistent / "dummy_load_resistance").write_text("42.5", encoding="utf-8")
    interaction = _RecordingInteraction(choice=False)
    monkeypatch.setattr("measure.util.measure_util.PROJECT_DIR", tmp_path)
    measure_util = MeasureUtil(MagicMock(PowerMeter), mock_config_factory(), interaction=interaction)

    assert measure_util.initialize_dummy_load() == pytest.approx(42.5)
    assert interaction.notifications


def test_dummy_load_requires_voltage_support(mock_config_factory: MockConfigFactory) -> None:
    power_meter = MagicMock(PowerMeter)
    power_meter.has_voltage_support.return_value = False
    measure_util = MeasureUtil(power_meter, mock_config_factory())

    with pytest.raises(UnsupportedFeatureError):
        measure_util._validate_voltage_support()  # noqa: SLF001


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
    measure_util = MeasureUtil(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count > 1 else 0.0

    result = measure_util.take_average_measurement(duration=10)

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
    measure_util = MeasureUtil(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count > 3 else 0.0

    result = measure_util.take_average_measurement(duration=10)

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
    measure_util = MeasureUtil(power_meter, mock_config)

    with pytest.raises(ApiConnectionError):
        measure_util.take_average_measurement(duration=10)

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
    measure_util = MeasureUtil(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if call_count >= 4 else 0.0

    result = measure_util.take_average_measurement(duration=10)

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
    measure_util = MeasureUtil(power_meter, mock_config)

    mock_time.side_effect = lambda: 100.0 if power_meter.call_count >= 3 else 0.0

    result = measure_util.take_average_measurement(duration=10)

    # Average should be exactly 7.0 since all successful readings are 7.0
    assert result.power == 7.0
