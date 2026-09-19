from measure.controller.light.capabilities import common_effects, merge_light_infos, supported_light_modes
from measure.controller.light.const import LutMode
from measure.controller.light.controller import LightInfo
import pytest


@pytest.mark.parametrize(
    "supported_color_modes, effects, expected",
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


def test_merge_light_infos_requires_at_least_one_light() -> None:
    with pytest.raises(ValueError, match="empty set of light infos"):
        merge_light_infos([])


def test_merge_light_infos_uses_the_shared_temperature_range() -> None:
    info = merge_light_infos([LightInfo("one", 150, 450), LightInfo("two", 200, 500)])

    assert info.min_mired == 200
    assert info.max_mired == 450


@pytest.mark.parametrize(
    "effects, expected",
    [
        ([], []),
        ([["candle", "rainbow"]], ["candle", "rainbow"]),
        ([["rainbow", "candle"], ["candle", "rainbow"]], ["rainbow", "candle"]),
        ([["rainbow"], []], []),
    ],
)
def test_common_effects_preserves_order_and_requires_support_from_every_light(
    effects: list[list[str]],
    expected: list[str],
) -> None:
    assert common_effects(effects) == expected
