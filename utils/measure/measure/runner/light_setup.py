from collections.abc import Callable
import logging

from measure.controller.errors import ApiConnectionError
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController, LightInfo
from measure.runner.errors import RunnerError

_LOGGER = logging.getLogger("measure")

MAX_RETRIES = 5
RETRY_DELAY = 5


def set_light_to_maximum_brightness(
    controller: LightController,
    light_info: LightInfo,
    mode: LutMode,
    *,
    sleep_time: float,
    wait: Callable[[float], None],
    checkpoint: Callable[[], None] | None = None,
) -> None:
    """Set maximum brightness twice for lights that turn off after rapid commands."""

    kwargs: dict[str, int] = {"bri": 255}
    if mode == LutMode.HS:
        kwargs.update(hue=0, sat=1)
    elif mode == LutMode.COLOR_TEMP:
        kwargs["ct"] = light_info.min_mired
    else:
        mode = LutMode.BRIGHTNESS

    _LOGGER.info("Turning on light with maximum brightness")
    for _ in range(2):
        if checkpoint is not None:
            checkpoint()
        _change_light_state_with_retry(controller, mode, wait, **kwargs)
        wait(sleep_time)


def _change_light_state_with_retry(
    controller: LightController,
    mode: LutMode,
    wait: Callable[[float], None],
    **kwargs: int,
) -> None:
    """Retry the initial turn-on the same way the measurement loop retries variations.

    This call runs before any variation is measured, so an unhandled ApiConnectionError
    here aborts the whole session before a single row is written.
    """
    for _ in range(MAX_RETRIES):
        try:
            controller.change_light_state(mode, on=True, **kwargs)
            return
        except ApiConnectionError as error:
            _LOGGER.warning("Failed to change light state: %s. Retrying...", error)
            wait(RETRY_DELAY)
    raise RunnerError(f"Failed to change light state after {MAX_RETRIES} retries")
