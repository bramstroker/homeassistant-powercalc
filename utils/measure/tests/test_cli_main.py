from unittest.mock import patch

from inquirer.errors import ValidationError
from measure.cli.main import main, validate_required
from measure.controller.errors import ControllerError
from measure.powermeter.errors import PowerMeterError
from measure.runner.errors import RunnerError
from measure.utils.version import measure_version
import pytest


def test_cli_exits_successfully_after_measurement(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("measure.cli.main.Measure") as measure, pytest.raises(SystemExit) as raised:
        main()

    assert raised.value.code == 0
    measure.return_value.start.assert_called_once_with()
    assert f"Powercalc measure: {measure_version()}" in capsys.readouterr().out


@pytest.mark.parametrize(
    "error", [PowerMeterError("Meter offline"), ControllerError("Device offline"), RunnerError("Sampling failed")]
)
def test_cli_reports_measurement_failure_and_exits(error: Exception, caplog: pytest.LogCaptureFixture) -> None:
    with patch("measure.cli.main.Measure") as measure:
        measure.return_value.start.side_effect = error
        with pytest.raises(SystemExit) as raised:
            main()

    assert raised.value.code == 1
    assert "Aborting" in caplog.text
    assert str(error) in caplog.text


def test_cli_reports_user_interruption(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("measure.cli.main.Measure") as measure:
        measure.return_value.start.side_effect = KeyboardInterrupt
        with pytest.raises(SystemExit) as raised:
            main()

    assert raised.value.code == 1
    assert "Aborted" in capsys.readouterr().out


def test_cli_preserves_unexpected_errors() -> None:
    error = RuntimeError("Unexpected failure")
    with patch("measure.cli.main.Measure") as measure:
        measure.return_value.start.side_effect = error
        with pytest.raises(RuntimeError) as raised:
            main()

    assert raised.value is error


def test_required_answer_rejects_empty_input() -> None:
    with pytest.raises(ValidationError) as raised:
        validate_required({}, "")

    assert "This question cannot be empty" in raised.value.reason


def test_required_answer_accepts_input() -> None:
    assert validate_required({}, "Shelly Plug S") is True
