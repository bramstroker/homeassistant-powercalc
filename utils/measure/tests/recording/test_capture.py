from measure.recording.capture import vacuum_recording_attributes
import pytest


@pytest.mark.parametrize(
    "value, included",
    [
        (True, True),
        (False, True),
        (4, True),
        (2.5, True),
        ("Active", True),
        ("x" * 512, True),
        ("x" * 513, False),
        (None, False),
        (float("nan"), False),
        (float("inf"), False),
        ({"ip": "private"}, False),
        (["map"], False),
        ("https://example.com/image", False),
        ("http://example.com/image", False),
        ("data:image/png;base64,payload", False),
    ],
)
def test_vacuum_attributes_keep_only_bounded_analysis_values(value: object, included: bool) -> None:
    assert vacuum_recording_attributes({"washing": value}) == ({"washing": value} if included else {})


def test_vacuum_attributes_exclude_identifying_metadata() -> None:
    assert vacuum_recording_attributes(
        {
            "ssid": "private",
            "ip": "private",
            "friendly_name": "private",
            "access_token": "private",
            "entity_picture": "/api/image/private",
            "drying_time": 2,
            "washing": True,
        }
    ) == {"drying_time": 2, "washing": True}
