from unittest.mock import MagicMock, call

from measure.cancellation import MeasurementCancelledError
from measure.controller.errors import ApiConnectionError
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController, LightInfo
from measure.runner.errors import RunnerError
from measure.runner.light.runner import LightControl
import pytest


@pytest.mark.parametrize(
    "mode, expected_mode, settings",
    [
        (LutMode.BRIGHTNESS, LutMode.BRIGHTNESS, {"bri": 255}),
        (LutMode.HS, LutMode.HS, {"bri": 255, "hue": 0, "sat": 1}),
        (LutMode.COLOR_TEMP, LutMode.COLOR_TEMP, {"bri": 255, "ct": 160}),
        (LutMode.WHITE, LutMode.BRIGHTNESS, {"bri": 255}),
        (LutMode.EFFECT, LutMode.BRIGHTNESS, {"bri": 255}),
    ],
)
def test_maximum_brightness_sets_mode_twice(mode: LutMode, expected_mode: LutMode, settings: dict[str, int]) -> None:
    controller = MagicMock(spec=LightController)
    wait = MagicMock()
    checkpoint = MagicMock()
    control = LightControl(controller, wait=wait, checkpoint=checkpoint)

    control.set_maximum_brightness(LightInfo("test", min_mired=160), mode, sleep_time=2)

    assert controller.change_light_state.call_args_list == [call(expected_mode, on=True, **settings)] * 2
    assert wait.call_args_list == [call(2)] * 2
    assert checkpoint.call_count == 2


def test_light_command_retries_connection_failures_with_unchanged_settings() -> None:
    controller = MagicMock(spec=LightController)
    controller.change_light_state.side_effect = [ApiConnectionError("Disconnected"), None]
    wait = MagicMock()
    checkpoint = MagicMock()

    control = LightControl(controller, wait=wait, checkpoint=checkpoint)
    control.change_state_with_retry(LutMode.EFFECT, bri=100, effect="Pulse")

    assert controller.change_light_state.call_args_list == [call(LutMode.EFFECT, on=True, bri=100, effect="Pulse")] * 2
    wait.assert_called_once_with(5)
    assert checkpoint.call_count == 2


def test_light_command_stops_after_five_attempts_and_preserves_cause() -> None:
    controller = MagicMock(spec=LightController)
    error = ApiConnectionError("Disconnected")
    controller.change_light_state.side_effect = error
    wait = MagicMock()

    control = LightControl(controller, wait=wait)
    with pytest.raises(RunnerError, match="after 5 retries") as raised:
        control.change_state_with_retry(LutMode.BRIGHTNESS, bri=100)

    assert raised.value.__cause__ is error
    assert controller.change_light_state.call_count == 5
    assert wait.call_args_list == [call(5)] * 5


def test_light_command_does_not_retry_unrelated_errors() -> None:
    controller = MagicMock(spec=LightController)
    controller.change_light_state.side_effect = ValueError("Invalid brightness")
    wait = MagicMock()

    control = LightControl(controller, wait=wait)
    with pytest.raises(ValueError, match="Invalid brightness"):
        control.change_state_with_retry(LutMode.BRIGHTNESS, bri=100)

    controller.change_light_state.assert_called_once()
    wait.assert_not_called()


@pytest.mark.parametrize("during_setup", [False, True])
def test_light_retries_stop_when_cancelled(during_setup: bool) -> None:
    controller = MagicMock(spec=LightController)
    controller.change_light_state.side_effect = ApiConnectionError("Disconnected")
    wait = MagicMock()
    checkpoint = MagicMock(side_effect=[None, MeasurementCancelledError()])
    control = LightControl(controller, wait=wait, checkpoint=checkpoint)

    if during_setup:
        with pytest.raises(MeasurementCancelledError):
            control.set_maximum_brightness(LightInfo("test"), LutMode.BRIGHTNESS, sleep_time=2)
    else:
        with pytest.raises(MeasurementCancelledError):
            control.change_state_with_retry(LutMode.BRIGHTNESS, bri=100)

    controller.change_light_state.assert_called_once()
    wait.assert_called_once_with(5)
