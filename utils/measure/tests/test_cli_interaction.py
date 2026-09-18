from unittest.mock import MagicMock

from measure.cli.interaction import ConsoleInteraction
import pytest


@pytest.mark.parametrize(
    "answer, default, expected",
    [
        ("", True, True),
        ("  ", False, False),
        (" y ", False, True),
        (" YES ", False, True),
        ("n", True, False),
        ("no", True, False),
        ("other", True, False),
    ],
)
def test_console_choice_normalizes_answer_and_shows_default(
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
    default: bool,
    expected: bool,
) -> None:
    prompt = MagicMock(return_value=answer)
    monkeypatch.setattr("builtins.input", prompt)

    assert ConsoleInteraction().choose("Repeat?", default=default) is expected
    suffix = "Y/n" if default else "y/N"
    prompt.assert_called_once_with(f"Repeat? [{suffix}] ")


def test_console_confirmation_waits_for_operator(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt = MagicMock(return_value="")
    monkeypatch.setattr("builtins.input", prompt)

    ConsoleInteraction().confirm("Prepare the device", action="prepare")

    prompt.assert_called_once_with("Prepare the device\nPress enter to continue...")


def test_console_notifications_print_without_live_session_events(capsys: pytest.CaptureFixture[str]) -> None:
    interaction = ConsoleInteraction()
    interaction.notify("Measurement ready")
    interaction.phase("Measuring")
    interaction.progress(1, 2, phase="brightness", remaining_seconds=10, skipped=1)
    interaction.operating_point({"type": "fan", "percentage": 50, "on": True})
    interaction.entity_states({"vacuum.test": "cleaning"})
    interaction.checkpoint()

    assert capsys.readouterr().out == "Measurement ready\n"


def test_console_wait_uses_requested_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    wait = MagicMock()
    monkeypatch.setattr("measure.cli.interaction.time.sleep", wait)

    ConsoleInteraction().wait(1.5)

    wait.assert_called_once_with(1.5)
