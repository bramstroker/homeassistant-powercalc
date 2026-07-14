from measure.controller.light.capabilities import supported_light_modes
from measure.controller.light.const import LutMode
import pytest


@pytest.mark.parametrize(
    ("supported_color_modes", "effects", "expected"),
    [
        (["color_temp"], ["candle"], [LutMode.COLOR_TEMP, LutMode.EFFECT]),
        (
            ["color_temp", "xy"],
            ["candle"],
            [LutMode.COLOR_TEMP, LutMode.HS, LutMode.EFFECT],
        ),
        (["rgb"], [], [LutMode.HS]),
        (["brightness"], [], [LutMode.BRIGHTNESS]),
        (["onoff"], [], []),
    ],
)
def test_supported_light_modes_normalizes_home_assistant_color_modes(
    supported_color_modes: list[str],
    effects: list[str],
    expected: list[LutMode],
) -> None:
    attributes = {
        "supported_color_modes": supported_color_modes,
        "effect_list": effects,
    }

    assert supported_light_modes(attributes) == expected
