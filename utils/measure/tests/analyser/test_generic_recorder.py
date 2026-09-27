import ast
from dataclasses import replace
import json
from pathlib import Path

from jsonschema import validate
from measure.analyser.service import RecorderAnalyser
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.profile.device_type import PROFILE_DEVICE_DOMAINS, ProfileDeviceType
from measure.recording.context import build_recording_context
from measure.recording.models import RecordedEntity, RecorderProfileRecipe, RecordingContext
from measure.request import RecorderMeasurementRequest
from pydantic import ValidationError
import pytest


def camera_context() -> RecordingContext:
    return RecordingContext(
        recipe=RecorderProfileRecipe.GENERIC,
        primary_entity_id="camera.porch",
        device_type="camera",
        entities=[
            RecordedEntity("camera.porch", "camera", "primary", device_id="camera"),
            RecordedEntity(
                "sensor.porch_mode", "sensor", "tracked", device_id="camera", translation_key="day_night_state"
            ),
        ],
    )


def record_camera(
    path: Path,
    context: RecordingContext,
    states: dict[str, float],
    *,
    samples_per_state: int = 10,
) -> Path:
    records = [context.build_metadata_record()]
    for state, power in states.items():
        for index in range(samples_per_state):
            records.append(
                {
                    "record_type": "sample",
                    "elapsed_seconds": (len(records) - 1) * 2,
                    "power": power + (0.04 if index % 2 else -0.04),
                    "entities": {
                        "camera.porch": {"state": "idle", "attributes": {}},
                        "sensor.porch_mode": {"state": state, "attributes": {}},
                    },
                }
            )
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    return path


def test_secondary_state_generates_portable_profile_with_independent_validation(tmp_path: Path) -> None:
    context = camera_context()
    training = record_camera(tmp_path / "first.jsonl", context, {"day": 2, "night": 5})
    validation = record_camera(tmp_path / "latest.jsonl", context, {"night": 5.1, "day": 2.1})
    # Replay resolves references from saved metadata, without a live HA catalog.
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        primary_entity_id="camera.porch",
        profile_device_type="camera",
        tracked_entity_ids=["sensor.porch_mode"],
    )
    result = RecorderAnalyser().analyse([training, validation], build_recording_context(request))

    assert result.model_ready, result.reason
    assert result.validation_method == "held_out_recording"
    assert result.metrics is not None
    assert result.metrics.mae_w == pytest.approx(0.1)
    assert result.metrics.validation_count == 20
    assert result.feature is not None
    assert result.feature.identifier == "sensor.porch_mode.state"
    assert result.standby_power is None
    assert result.model_config_fragment is not None
    model = result.model_config_fragment.to_dict()
    assert model == {
        "calculation_strategy": "composite",
        "composite_config": {
            "mode": "stop_at_first",
            "strategies": [
                {
                    "condition": {
                        "condition": "state",
                        "entity_id": "[[entity_by_translation_key:day_night_state]]",
                        "state": state,
                    },
                    "fixed": {"power": power, "states_power": {"off": power}},
                }
                for state, power in {"day": 2.0, "night": 5.0}.items()
            ],
        },
    }
    schema = json.loads((Path(__file__).parents[4] / "profile_library/model_schema.json").read_text())
    validate(
        {
            "name": "Camera",
            "device_type": context.device_type,
            "measure_method": "script",
            "measure_device": "Test meter",
            "created_at": "2026-09-27T00:00:00Z",
            **model,
        },
        schema,
    )
    assert result.build_summary()["Recording analysis"] == "State-based composite profile created"
    assert result.build_summary()["Validation method"] == "held_out_recording"


@pytest.mark.parametrize(
    "latest,reason",
    [
        ({"day": 2}, "every learned state"),
        ({"day": 2, "night": 20}, "did not repeat reliably"),
        ({"day": 2, "night": 5, "unknown": 8}, "could estimate"),
        ({"day": 2, "night": 5, "new_mode": 8}, "could estimate"),
    ],
)
def test_latest_run_must_validate_all_states_without_learning_from_it(
    tmp_path: Path, latest: dict[str, float], reason: str
) -> None:
    context = camera_context()
    paths = [
        record_camera(tmp_path / "first.jsonl", context, {"day": 2, "night": 5}),
        record_camera(tmp_path / "latest.jsonl", context, latest),
    ]
    result = RecorderAnalyser().analyse(paths, context)
    assert not result.model_ready
    assert reason in str(result.reason)


def test_single_recording_requires_record_more_even_with_many_samples(tmp_path: Path) -> None:
    context = camera_context()
    path = record_camera(tmp_path / "record.jsonl", context, {"day": 2, "night": 5}, samples_per_state=100)
    result = RecorderAnalyser().analyse(path, context)
    assert not result.model_ready
    assert "Record more" in str(result.reason)


def test_portable_secondary_signal_still_needs_five_training_samples_per_state(tmp_path: Path) -> None:
    context = camera_context()
    paths = [
        record_camera(tmp_path / name, context, {"day": 2, "night": 5}, samples_per_state=3)
        for name in ["a.jsonl", "b.jsonl"]
    ]

    result = RecorderAnalyser().analyse(paths, context)

    assert not result.model_ready
    assert "at least 5 training samples per value" in str(result.reason)


def test_secondary_signal_on_parent_device_generates_portable_profile(tmp_path: Path) -> None:
    context = camera_context()
    primary, secondary = context.entities
    context = replace(
        context,
        entities=[primary, replace(secondary, device_id="camera-parent")],
        related_device_ids=["camera-parent"],
    )
    paths = [record_camera(tmp_path / name, context, {"day": 2, "night": 5}) for name in ["a.jsonl", "b.jsonl"]]

    result = RecorderAnalyser().analyse(paths, context)

    assert result.model_ready, result.reason
    assert result.feature is not None
    assert result.feature.identifier == "sensor.porch_mode.state"
    assert result.model_config_fragment is not None
    condition = result.model_config_fragment.to_dict()["composite_config"]["strategies"][0]["condition"]
    assert condition["entity_id"] == "[[entity_by_translation_key:day_night_state]]"


@pytest.mark.parametrize("problem", ["unrelated", "ambiguous", "missing_metadata"])
def test_secondary_signal_requires_portable_reference(tmp_path: Path, problem: str) -> None:
    context = camera_context()
    primary, secondary = context.entities
    if problem == "unrelated":
        context = replace(context, entities=[primary, replace(secondary, device_id="unrelated")])
    elif problem == "ambiguous":
        context = replace(
            context, device_entities=[*context.entities, replace(secondary, entity_id="sensor.duplicate")]
        )
    else:
        context = replace(context, entities=[primary, replace(secondary, translation_key=None)])
    paths = [record_camera(tmp_path / name, context, {"day": 2, "night": 5}) for name in ["a.jsonl", "b.jsonl"]]
    result = RecorderAnalyser().analyse(paths, context)
    assert not result.model_ready
    assert "portable entity reference" in str(result.reason)


def test_request_explicit_primary_and_device_type_round_trip() -> None:
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        primary_entity_id="camera.porch",
        profile_device_type="camera",
        tracked_entity_ids=["sensor.mode"],
    )
    restored = RecorderMeasurementRequest.model_validate_json(request.model_dump_json())
    assert restored.recorded_entity_ids == ["camera.porch", "sensor.mode"]
    context = build_recording_context(restored)
    assert context.primary_entity_id == "camera.porch"
    assert context.device_type == "camera"


def test_legacy_request_promotes_first_entity_and_preserves_capture_order() -> None:
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        tracked_entity_ids=["camera.porch", "sensor.mode"],
    )
    assert request.primary_entity_id == "camera.porch"
    assert request.tracked_entity_ids == ("sensor.mode",)
    assert request.recorded_entity_ids == ["camera.porch", "sensor.mode"]
    assert build_recording_context(request).device_type == "generic_iot"


@pytest.mark.parametrize(
    "overrides",
    [
        {"primary_entity_id": "bad id"},
        {"primary_entity_id": None},
        {"tracked_entity_ids": ["camera.porch"]},
        {"profile_device_type": "unsupported"},
        {"profile_device_type": "vacuum_robot"},
        {"profile_device_type": "camera", "primary_entity_id": "sensor.porch"},
        {"tracked_entity_ids": [f"sensor.signal_{i}" for i in range(100)]},
        {"recorder_purpose": "playbook", "profile_recipe": None},
        {"profile_recipe": "vacuum_robot", "vacuum_entity_id": "vacuum.robot", "battery_entity_id": "sensor.battery"},
    ],
)
def test_invalid_generic_request_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RecorderMeasurementRequest.model_validate(
            {
                "power_meter": {"type": "dummy"},
                "recorder_purpose": "complex_profile",
                "profile_recipe": "generic",
                "primary_entity_id": "camera.porch",
                **overrides,
            }
        )


def test_profile_device_types_match_library_schema() -> None:
    schema = json.loads((Path(__file__).parents[4] / "profile_library/model_schema.json").read_text())
    assert set(ProfileDeviceType) == set(schema["properties"]["device_type"]["enum"])


@pytest.mark.parametrize(
    "device_type,primary_entity_id",
    [("camera", "camera.porch"), ("smart_switch", "switch.plug"), ("smart_switch", "light.plug")],
)
def test_generic_request_accepts_mapped_primary_domain(device_type: str, primary_entity_id: str) -> None:
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="generic",
        profile_device_type=device_type,
        primary_entity_id=primary_entity_id,
    )
    assert request.primary_entity_id == primary_entity_id


def test_profile_device_domains_match_integration_mapping() -> None:
    integration = Path(__file__).parents[4] / "custom_components/powercalc/power_profile/power_profile.py"
    tree = ast.parse(integration.read_text())
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "DEVICE_TYPE_DOMAIN"
    )
    assert isinstance(assignment.value, ast.Dict)
    actual: dict[ProfileDeviceType, set[str]] = {}
    for key, value in zip(assignment.value.keys, assignment.value.values, strict=True):
        assert isinstance(key, ast.Attribute)
        members = value.elts if isinstance(value, ast.Set) else [value]
        assert all(isinstance(member, ast.Name) for member in members)
        actual[ProfileDeviceType(key.attr.lower())] = {
            member.id.removesuffix("_DOMAIN").lower() for member in members if isinstance(member, ast.Name)
        }
    assert actual == {device_type: set(domains) for device_type, domains in PROFILE_DEVICE_DOMAINS.items()}
