from collections.abc import Callable
import logging

from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightController, LightInfo

_LOGGER = logging.getLogger("measure")


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
        controller.change_light_state(mode, on=True, **kwargs)
        wait(sleep_time)
