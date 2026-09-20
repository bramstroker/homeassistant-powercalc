import json
from pathlib import Path

from measure.ha_app.contribution.models import ContributionApiError, ContributionAuthStatus
from measure.ha_app.contribution.preview import (
    _build_preview_file,
    _prepared_model,
    draft_from_request,
    metadata_from_request,
)
from measure.profile.models import RenderedProfileFile
from measure.request import MeasurementRequest, parse_measurement_request
import pytest


@pytest.fixture
def request_model() -> MeasurementRequest:
    return parse_measurement_request(
        {
            "measure_type": "recorder",
            "model_id": "test",
            "product_name": "Test device",
            "power_meter": {"type": "dummy"},
        }
    )


def test_metadata_defaults_to_request_and_authenticated_author(request_model: MeasurementRequest) -> None:
    metadata = metadata_from_request(request_model, None, ContributionAuthStatus(authenticated=True, username="octo"))
    assert metadata.manufacturer == "Unknown"
    assert metadata.model_id == "test"
    assert metadata.author.github == "octo"
    assert metadata.measure_device == request_model.measure_device


def test_metadata_requires_github_identity(request_model: MeasurementRequest) -> None:
    with pytest.raises(ContributionApiError, match="GitHub username is required") as error:
        metadata_from_request(request_model, None, ContributionAuthStatus(authenticated=False))
    assert error.value.field == "contributor_github"


def test_draft_without_artifact_directory(request_model: MeasurementRequest, tmp_path: Path) -> None:
    preview = draft_from_request(
        session_id="session",
        request=request_model,
        artifact_root=tmp_path / "missing",
        auth=ContributionAuthStatus(authenticated=False),
    )
    assert preview.files == []


@pytest.mark.parametrize(
    "specs,detected,expected",
    [
        (None, "zigbee", {"connectivity": ["zigbee"]}),
        ({"rated_power": 9}, "zigbee", {"rated_power": 9, "connectivity": ["zigbee"]}),
        ({"connectivity": ["wifi", "bluetooth"]}, "zigbee", {"connectivity": ["wifi", "bluetooth"]}),
        ({"connectivity": []}, "zigbee", {"connectivity": []}),
        ({"connectivity": None}, "zigbee", {"connectivity": None}),
        (None, None, None),
        ({"rated_power": 9}, None, {"rated_power": 9}),
    ],
)
def test_connectivity_only_defaults_when_absent(
    request_model: MeasurementRequest,
    tmp_path: Path,
    specs: dict[str, object] | None,
    detected: str | None,
    expected: dict[str, object] | None,
) -> None:
    artifact = {"device_specs": specs}
    (tmp_path / "model.json").write_text(json.dumps(artifact))
    preview = draft_from_request(
        session_id="session",
        request=request_model,
        artifact_root=tmp_path,
        auth=ContributionAuthStatus(authenticated=False),
        default_connectivity=detected,
    )
    assert preview.device_specs == expected
    assert json.loads((tmp_path / "model.json").read_text()) == artifact


@pytest.mark.parametrize(
    "voltage_range,expected",
    [
        ({"min": 228, "max": 232}, {"min": 228.0, "max": 232.0}),
        ({"min": True, "max": 232}, None),
        ({"min": 232, "max": 228}, None),
        ({"min": "228", "max": 232}, None),
    ],
)
def test_draft_reads_artifact_author_and_voltage(
    request_model: MeasurementRequest, tmp_path: Path, voltage_range: object, expected: object
) -> None:
    (tmp_path / "model.json").write_text(
        json.dumps({"voltage_range": voltage_range, "authors": [{"name": "Octo", "github": "octo"}]})
    )
    preview = draft_from_request(
        session_id="session",
        request=request_model,
        artifact_root=tmp_path,
        auth=ContributionAuthStatus(authenticated=False),
    )
    assert preview.contributor == "Octo"
    assert preview.voltage_range == expected
    if expected is not None:
        assert preview.mains_voltage == 230


@pytest.mark.parametrize(
    "contents", [[], [RenderedProfileFile("model.json", b"invalid")], [RenderedProfileFile("model.json", b"[]")]]
)
def test_missing_or_invalid_prepared_model_is_empty(contents: list[RenderedProfileFile]) -> None:
    assert _prepared_model(contents) == {}


@pytest.mark.parametrize(
    "filename,content,expected_text", [("readme.txt", b"Notes", "Notes"), ("data.gz", b"binary", None)]
)
def test_preview_distinguishes_text_and_binary_files(filename: str, content: bytes, expected_text: str | None) -> None:
    preview = _build_preview_file(filename, content)
    assert preview.content == expected_text
    assert preview.size == len(content)
