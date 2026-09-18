from measure.visualization.labels import format_entity_label, format_value_label
import pytest


@pytest.mark.parametrize(
    "entity_id, expected",
    [
        ("[[entity]]", "state"),
        ("[[entity_by_translation_key:charging_state]]", "charging state"),
        ("[[charging_state]]", "charging state"),
        ("sensor.charging_state", "sensor.charging state"),
        (["[[entity]]", "sensor.other"], "state"),
        ([], None),
        ([None], None),
        (None, None),
        (42, None),
    ],
)
def test_format_entity_label(entity_id: object, expected: str | None) -> None:
    assert format_entity_label(entity_id) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (["on", "starting"], "on, starting"),
        ([], ""),
        (True, "true"),
        (False, "false"),
        ("docked", "docked"),
        (42, "42"),
    ],
)
def test_format_value_label(value: object, expected: str) -> None:
    assert format_value_label(value) == expected
