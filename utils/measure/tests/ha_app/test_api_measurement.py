from collections.abc import Callable, Sequence
import json
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from measure.const import MeasureType
from measure.ha_app.api import create_app
from measure.ha_app.contribution.coordinator import ContributionApiCoordinator
from measure.ha_app.coordinator import (
    MeasurementCoordinator,
    SessionConflictError,
)
from measure.ha_app.light_probe import LightLoadProbeError
from measure.ha_app.session import SessionEvent, SessionEventType, SessionSnapshot, SessionState
from measure.ha_app.storage import SessionStorage
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import MeasurementRequest, RecorderMeasurementRequest, RecorderProfileRecipe, RecorderPurpose
from pydantic import TypeAdapter
import pytest

from tests.ha_app.api_test_support import (
    AppClientFactory,
    FakeContributionService,
    SummaryService,
    payload,
)


def test_measure_definitions_and_average_request(app_client: TestClient) -> None:

    definitions = app_client.get("/api/measure-definitions")
    assert definitions.status_code == 200
    assert {item["measure_type"] for item in definitions.json()} == {item.value for item in MeasureType}
    actions = {item["measure_type"]: item["confirmation_action"] for item in definitions.json()}
    assert actions == {
        "light": None,
        "speaker": "Start speaker measurement",
        "recorder": "Start recording",
        "average": "Start averaging",
        "charging": "Start charging measurement",
        "fan": None,
    }
    charging = next(item for item in definitions.json() if item["measure_type"] == MeasureType.CHARGING)
    fields = {field["name"]: field for field in charging["fields"]}
    assert "entity_domain" not in fields["charging_entity_id"]
    assert [
        (option["value"], option["label"], option["entity_domain"])
        for option in fields["charging_device_type"]["options"]
    ] == [
        ("vacuum_robot", "Vacuum robot", "vacuum"),
        ("lawn_mower_robot", "Lawn mower robot", "lawn_mower"),
    ]
    recorder = next(item for item in definitions.json() if item["measure_type"] == MeasureType.RECORDER)
    recorder_fields = {field["name"]: field for field in recorder["fields"]}
    assert recorder_fields["recorder_purpose"]["options"][0]["value"] == "playbook"
    assert recorder_fields["profile_recipe"]["visible_when"] == {"recorder_purpose": ["complex_profile"]}
    assert recorder_fields["tracked_entity_ids"]["all_entities"] is True
    assert recorder_fields["battery_entity_id"]["same_device_only"] is True

    payload = {
        "measure_type": MeasureType.AVERAGE,
        "power_meter": {"type": "hass", "entity_id": "sensor.test_power"},
        "duration": 60,
    }
    assert app_client.post("/api/preflight", json=payload).status_code == 200
    assert app_client.post("/api/sessions", json=payload).status_code == 201


def test_preflight_exposes_quality_warnings_and_start_reuses_diagnostics(app_client: TestClient) -> None:
    home_assistant = app_client.app.state.context.home_assistant

    response = app_client.post("/api/preflight", json=payload())

    assert response.status_code == 200
    assert response.json()["power_meter_diagnostic"]["precision_status"] == "good"
    assert response.json()["power_meter_diagnostic"]["update_interval_status"] == "poor"
    assert response.json()["light_load_probe"] == {
        "checked_variations": 1,
        "minimum_aggregate_power_w": 1.25,
        "points": [{"label": "Brightness 1", "mode": "brightness", "power_w": 1.25}],
    }
    assert "did not report often enough" in response.json()["warnings"][0]
    assert home_assistant.state_calls == 2
    assert app_client.post("/api/sessions", json=payload()).status_code == 201
    assert home_assistant.state_calls == 2


def test_preflight_maps_low_load_probe_failure_to_actionable_error(app_client: TestClient) -> None:
    app_client.app.state.context.light_load_probe.evaluate.side_effect = LightLoadProbeError(
        "The power meter repeatedly returned 0 W while checking the selected light",
        help_url="https://docs.powercalc.nl/contributing/measure/low-power-measurements/",
        help_label="Low-power measurement guide",
    )

    response = app_client.post("/api/preflight", json=payload())

    assert response.status_code == 422
    assert response.json() == {
        "code": "preflight_failed",
        "message": "The power meter repeatedly returned 0 W while checking the selected light",
        "field": None,
        "help_url": "https://docs.powercalc.nl/contributing/measure/low-power-measurements/",
        "help_label": "Low-power measurement guide",
    }


def test_preflight_does_not_attribute_probe_adapter_failures_to_low_power(app_client: TestClient) -> None:
    app_client.app.state.context.light_load_probe.evaluate.side_effect = LightLoadProbeError(
        "Could not complete the active light check: connection refused",
    )

    response = app_client.post("/api/preflight", json=payload())

    assert response.status_code == 422
    assert response.json() == {
        "code": "preflight_failed",
        "message": "Could not complete the active light check: connection refused",
        "field": None,
    }


def test_preflight_rejects_unavailable_entity(app_client: TestClient) -> None:

    response = app_client.post(
        "/api/preflight",
        json=payload() | {"power_meter": {"type": "hass", "entity_id": "sensor.missing"}},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "preflight_failed"


def test_preflight_rejects_cli_only_power_meter_adapter(app_client: TestClient) -> None:
    response = app_client.post(
        "/api/preflight",
        json={
            "measure_type": "average",
            "power_meter": {"type": "tasmota", "device_ip": "192.0.2.1"},
            "duration": 60,
        },
    )

    assert response.status_code == 422
    assert response.json()["message"] == "Tasmota power meters are not supported by the Home Assistant app"


def test_preflight_rejects_cli_only_controller_adapter(app_client: TestClient) -> None:
    request = payload()
    request["controller"] = {"type": "hue", "bridge_ip": "192.0.2.2", "light": "1"}

    response = app_client.post("/api/preflight", json=request)

    assert response.status_code == 422
    assert response.json()["message"] == "Hue light controllers are not supported by the Home Assistant app"


def test_preflight_allows_dummy_adapters_only_in_developer_mode(app_client_factory: AppClientFactory) -> None:
    request = {
        "measure_type": "average",
        "power_meter": {"type": "dummy"},
        "duration": 1,
    }

    rejected = app_client_factory().post("/api/preflight", json=request)
    accepted = app_client_factory(developer_mode=True).post("/api/preflight", json=request)

    assert rejected.status_code == 422
    assert rejected.json()["message"] == "Dummy power meters require developer mode in the Home Assistant app"
    assert accepted.status_code == 200


@pytest.mark.parametrize("entity_id", ["sensor.unknown_power", "sensor.text_power"])
def test_preflight_rejects_non_numeric_power_state(app_client: TestClient, entity_id: str) -> None:
    response = app_client.post(
        "/api/preflight",
        json=payload() | {"power_meter": {"type": "hass", "entity_id": entity_id}},
    )

    assert response.status_code == 422


def test_preflight_rejects_active_session(app_client: TestClient) -> None:
    coordinator = app_client.app.state.context.coordinator
    now = "2026-07-12T12:00:00Z"
    coordinator._snapshot = SessionSnapshot(id="active", state=SessionState.RUNNING, created_at=now, updated_at=now)  # noqa: SLF001

    response = app_client.post("/api/preflight", json=payload())

    assert response.status_code == 409


def test_session_start_conflict_after_preflight_returns_http_conflict(
    app_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = app_client.app.state.context.coordinator
    message = "A measurement session is already active"
    start = MagicMock(side_effect=SessionConflictError(message))
    monkeypatch.setattr(coordinator, "start", start)

    response = app_client.post("/api/sessions", json=payload())

    assert response.status_code == 409
    assert response.json()["message"] == message
    start.assert_called_once()
    assert coordinator.sessions() == []


def test_session_lifecycle_and_file_download(app_client: TestClient) -> None:

    response = app_client.post("/api/sessions", json=payload())

    assert response.status_code == 201
    session_id = response.json()["session_id"]
    current = {}
    for _ in range(50):
        current_response = app_client.get(f"/api/sessions/{session_id}")
        assert current_response.status_code == 200
        current = current_response.json()
        if current["state"] == "completed":
            break
        time.sleep(0.02)
    assert current["progress"]["estimated_remaining_seconds"] == 0
    assert current["operating_point"] == {"type": "light", "on": True, "brightness": 128}
    retained = app_client.get("/api/sessions")
    assert retained.status_code == 200
    assert retained.json()[0]["session_id"] == session_id
    assert retained.json()[0]["file_count"] == 1
    assert retained.json()[0]["size"] > 0
    files = app_client.get(f"/api/sessions/{session_id}/files")
    assert files.json()[0]["name"] == "LCT010/brightness.csv"
    plots = app_client.get(f"/api/sessions/{session_id}/plots")
    assert plots.status_code == 200
    assert plots.json()["partial"] is False
    assert plots.json()["warnings"] == []
    assert plots.json()["plots"][0]["id"] == "brightness"
    assert plots.json()["plots"][0]["series"][0]["points"] == [
        {"x": 1.0, "y": 1.0, "color": None},
    ]
    download = app_client.get(f"/api/sessions/{session_id}/files/LCT010/brightness.csv")
    assert download.status_code == 200
    diagnostics = app_client.get(f"/api/sessions/{session_id}/diagnostics")
    assert diagnostics.status_code == 200
    assert diagnostics.headers["content-disposition"].startswith('attachment; filename="powercalc-measure-diagnostics-')
    report = diagnostics.json()
    assert report["snapshot"]["state"] == "completed"
    assert report["request"]["model_id"] == "LCT010"
    assert report["request"]["controller"]["entity_id"] == "light.test"
    assert report["request"]["power_meter"]["entity_id"] == "sensor.test_power"
    assert report["logs"][0]["data"]["message"] == "Reading light.test with sensor.test_power"
    assert report["events"][-1]["data"]["state"] == "completed"
    assert report["files"][0]["name"] == "LCT010/brightness.csv"
    assert "test-token" not in diagnostics.text

    assert app_client.delete(f"/api/sessions/{session_id}").status_code == 204
    assert app_client.get(f"/api/sessions/{session_id}").status_code == 404
    assert app_client.get("/api/sessions").json() == []


@pytest.mark.parametrize("state", [SessionState.READY, SessionState.RUNNING])
def test_delete_rejects_active_session_and_preserves_it(app_client: TestClient, state: SessionState) -> None:
    context = app_client.app.state.context
    now = "2026-09-18T12:00:00Z"
    snapshot = SessionSnapshot(id="active-session", state=state, created_at=now, updated_at=now)
    request = TypeAdapter(MeasurementRequest).validate_python(payload())
    context.storage.create(snapshot, request)

    response = app_client.delete(f"/api/sessions/{snapshot.id}")

    assert response.status_code == 409
    assert response.json()["message"] == "An active measurement session cannot be deleted"
    assert app_client.get(f"/api/sessions/{snapshot.id}").json()["state"] == state.value


@pytest.mark.parametrize("name", ["missing.csv", "session.json", "%2e%2e/session.json"])
def test_download_rejects_missing_and_out_of_scope_files(app_client: TestClient, name: str) -> None:
    context = app_client.app.state.context
    now = "2026-09-18T12:00:00Z"
    snapshot = SessionSnapshot(id="download-session", state=SessionState.COMPLETED, created_at=now, updated_at=now)
    request = TypeAdapter(MeasurementRequest).validate_python(payload())
    context.storage.create(snapshot, request)

    response = app_client.get(f"/api/sessions/{snapshot.id}/files/{name}")

    assert response.status_code == 404
    assert response.json()["message"] == "File not found"


@pytest.mark.parametrize("estimate, expected_seconds", [(None, None), ("unknown", None), ("1.5m", 90), ("2h", 7200)])
def test_session_response_converts_saved_time_estimate(
    app_client: TestClient, estimate: str | None, expected_seconds: int | None
) -> None:
    context = app_client.app.state.context
    now = "2026-09-18T12:00:00Z"
    snapshot = SessionSnapshot(
        id="estimated-session",
        state=SessionState.COMPLETED,
        created_at=now,
        updated_at=now,
        estimated_remaining=estimate,
    )
    request = TypeAdapter(MeasurementRequest).validate_python(payload())
    context.storage.create(snapshot, request)

    response = app_client.get(f"/api/sessions/{snapshot.id}")

    assert response.status_code == 200
    assert response.json()["progress"]["estimated_remaining_seconds"] == expected_seconds


def test_diagnostics_retains_only_the_latest_thousand_events(app_client: TestClient) -> None:
    assert app_client.post("/api/sessions", json=payload()).status_code == 201
    coordinator = app_client.app.state.context.coordinator
    assert coordinator._worker is not None  # noqa: SLF001
    coordinator._worker.join(timeout=5)  # noqa: SLF001
    assert coordinator.current is not None
    events = tuple(
        SessionEvent(
            sequence=sequence,
            type=SessionEventType.LOG,
            created_at="2026-07-12T12:00:00Z",
            data={"message": str(sequence)},
        )
        for sequence in range(1, 1002)
    )
    storage = app_client.app.state.context.storage

    with patch.object(storage, "load_events", return_value=events) as load_events:
        response = app_client.get(f"/api/sessions/{coordinator.current.id}/diagnostics")

    assert response.status_code == 200
    load_events.assert_called_once_with(coordinator.current.id, limit=1001)
    report = response.json()
    assert len(report["events"]) == 1000
    assert report["events"][0]["sequence"] == 2
    assert report["events_truncated"] is True
    assert report["event_limit"] == 1000


def test_session_summary_is_exposed(app_client: TestClient, tmp_path: Path) -> None:
    app_client.app.state.context.coordinator = MeasurementCoordinator(SessionStorage(tmp_path), SummaryService)

    run_payload = {
        "measure_type": MeasureType.AVERAGE,
        "power_meter": {"type": "hass", "entity_id": "sensor.test_power"},
        "duration": 30,
    }
    started = app_client.post("/api/sessions", json=run_payload)
    assert started.status_code == 201
    session_id = started.json()["session_id"]

    current = {}
    for _ in range(50):
        current = app_client.get(f"/api/sessions/{session_id}").json()
        if current["state"] == "completed":
            break
        time.sleep(0.02)

    assert current["state"] == "completed"
    assert current["summary"] == {"Average power": "42.3 W", "Duration": "30 s"}


def test_completed_recording_can_be_analysed_again(app_client: TestClient) -> None:
    context = app_client.app.state.context
    request = RecorderMeasurementRequest(
        model_id="test-switch",
        product_name="Test switch",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose=RecorderPurpose.COMPLEX_PROFILE,
        profile_recipe=RecorderProfileRecipe.GENERIC,
        tracked_entity_ids=("switch.device",),
    )
    now = "2026-09-04T08:00:00Z"
    snapshot = SessionSnapshot(
        id="recorder-session",
        state=SessionState.COMPLETED,
        created_at=now,
        updated_at=now,
        summary={
            "Samples recorded": "20",
            "Recording analysis": "Failed",
            "Recording analysis reason": "Old analyser failed",
        },
    )
    context.storage.create(snapshot, request)
    output = context.storage.artifact_directory(snapshot.id, request.model_id)
    output.mkdir()
    records = [
        {
            "record_type": "sample",
            "elapsed_seconds": index,
            "power": 0.2 if index % 2 == 0 else 5.2,
            "entities": {"switch.device": {"state": "off" if index % 2 == 0 else "on", "attributes": {}}},
        }
        for index in range(20)
    ]
    (output / "record.jsonl").write_text(
        "".join(f"{json.dumps(record)}\n" for record in records),
        encoding="utf-8",
    )
    (output / "model.json").write_text(
        json.dumps({"voltage_range": {"min": 229.5, "max": 231.0}}),
        encoding="utf-8",
    )

    before = app_client.get(f"/api/sessions/{snapshot.id}")
    response = app_client.post(f"/api/sessions/{snapshot.id}/analyse")

    assert before.json()["can_analyse"] is True
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "completed"
    assert body["can_analyse"] is True
    assert body["summary"] == {
        "Samples recorded": "20",
        "Recording analysis": "Fixed power profile created",
        "Analysed feature": "switch.device.state",
        "Validation MAE": "0.00 W",
        "Validation coverage": "100%",
        "Recordings analysed": "1",
        "Samples analysed": "20",
    }
    model = json.loads((output / "model.json").read_text(encoding="utf-8"))
    assert model["fixed_config"] == {"power": 5.2}
    assert model["voltage_range"] == {"min": 229.5, "max": 231.0}


def test_analysed_recorder_profile_can_be_prepared(app_client: TestClient) -> None:
    context = app_client.app.state.context
    service = FakeContributionService()
    resolved_entities: list[tuple[str, ...]] = []

    def resolve(value: str) -> Callable[[Sequence[str]], dict[str, str]]:
        def resolver(entity_ids: Sequence[str]) -> dict[str, str]:
            resolved_entities.append(tuple(entity_ids))
            return dict.fromkeys(entity_ids, value)

        return resolver

    context.contribution = ContributionApiCoordinator(
        context.storage,
        service_factory=lambda: service,
        resolve_integration=resolve("tplink"),
        resolve_manufacturer=resolve("Acme"),
        resolve_model_id=resolve("HEATER-1"),
    )
    request = RecorderMeasurementRequest(
        session_name="Smart heater recording",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose=RecorderPurpose.COMPLEX_PROFILE,
        profile_recipe=RecorderProfileRecipe.GENERIC,
        tracked_entity_ids=("switch.heater", "sensor.heater_mode"),
    )
    now = "2026-09-06T08:00:00Z"
    snapshot = SessionSnapshot(
        id="recorder-profile",
        state=SessionState.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    context.storage.create(snapshot, request)
    artifacts = context.storage.artifact_directory(snapshot.id, request.model_id)
    artifacts.mkdir()
    (artifacts / "record.jsonl").write_text('{"record_type":"sample"}\n', encoding="utf-8")
    (artifacts / "analyser.json").write_text('{"status":"model_ready"}', encoding="utf-8")
    (artifacts / "model.json").write_text(
        json.dumps(
            {
                "name": "",
                "device_type": "generic_iot",
                "measure_device": "Test meter",
                "calculation_strategy": "fixed",
                "fixed_config": {"states_power": {"off": 0.4, "on": 9.8}},
            },
        ),
        encoding="utf-8",
    )

    draft = app_client.get(f"/api/sessions/{snapshot.id}/contribution")

    assert draft.status_code == 200
    assert draft.json()["eligible"] is True
    assert draft.json()["manufacturer_name"] == "Acme"
    assert draft.json()["model_id"] == "HEATER-1"
    assert draft.json()["product_name"] == ""
    assert draft.json()["home_assistant"] == {
        "measure_type": "recorder",
        "controlled_entity": "switch.heater",
        "integration": "tplink",
    }
    assert resolved_entities == [("switch.heater",)] * 3

    preview = app_client.post(
        f"/api/sessions/{snapshot.id}/contribution/preview",
        json={
            "manufacturer_name": "Acme",
            "model_id": "HEATER-1",
            "product_name": "Smart heater",
            "contributor": "Test User",
        },
    )

    assert preview.status_code == 200
    assert preview.json()["eligible"] is True
    assert service.preview_calls == 1


def test_playbook_recorder_is_not_a_profile_contribution(app_client: TestClient) -> None:
    context = app_client.app.state.context
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose=RecorderPurpose.PLAYBOOK,
    )
    now = "2026-09-06T08:00:00Z"
    snapshot = SessionSnapshot(
        id="recorder-playbook",
        state=SessionState.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    context.storage.create(snapshot, request)
    artifacts = context.storage.artifact_directory(snapshot.id, request.model_id)
    artifacts.mkdir()
    (artifacts / "model.json").write_text("{}", encoding="utf-8")

    draft = app_client.get(f"/api/sessions/{snapshot.id}/contribution")

    assert draft.status_code == 200
    assert draft.json()["eligible"] is False
    assert "analysed recorder profiles" in draft.json()["reason"]

    preview = app_client.post(
        f"/api/sessions/{snapshot.id}/contribution/preview",
        json={
            "manufacturer_name": "Acme",
            "model_id": "PLAYBOOK-1",
            "product_name": "Playbook recording",
            "contributor": "Test User",
        },
    )

    assert preview.status_code == 422
    assert preview.json()["code"] == "artifacts_required"


def test_analyse_rejects_a_session_without_a_profile_recording(app_client: TestClient) -> None:
    context = app_client.app.state.context
    request = RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec())
    now = "2026-09-04T08:00:00Z"
    snapshot = SessionSnapshot(
        id="playbook-session",
        state=SessionState.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    context.storage.create(snapshot, request)

    response = app_client.post(f"/api/sessions/{snapshot.id}/analyse")

    assert response.status_code == 409
    assert "no recording" in response.json()["message"]


def test_validation_errors_have_stable_shape(app_client: TestClient) -> None:
    response = app_client.post("/api/preflight", json=payload() | {"model_id": "../secret"})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["field"] == "model_id"


def test_openapi_contract_contains_the_supported_app_endpoints(tmp_path: Path) -> None:
    app = create_app(data_root=tmp_path, hass_token="test-token", trusted_ingress_only=False)  # noqa: S106

    contract = app.openapi()
    paths = contract["paths"]

    assert set(paths["/api/sessions"]) == {"get", "post"}
    assert set(paths["/api/library/measure-devices"]) == {"get"}
    assert set(paths["/api/library/device-specifications"]) == {"get"}
    assert set(paths["/api/sessions/{session_id}"]) == {"get", "delete"}
    assert set(paths["/api/sessions/{session_id}/cancel"]) == {"post"}
    assert set(paths["/api/sessions/{session_id}/confirm"]) == {"post"}
    assert set(paths["/api/sessions/{session_id}/resume"]) == {"post"}
    assert set(paths["/api/sessions/{session_id}/analyse"]) == {"post"}
    assert set(paths["/api/sessions/{session_id}/diagnostics"]) == {"get"}
    assert set(paths["/api/sessions/{session_id}/plots"]) == {"get"}
    assert set(paths["/api/sessions/{session_id}/files/{name}"]) == {"get"}
    assert set(paths["/api/sessions/{session_id}/contribution"]) == {"get", "post"}
    assert set(paths["/api/sessions/{session_id}/contribution/preview"]) == {"post"}
    assert set(paths["/api/sessions/{session_id}/contribution/{job_id}/profile.zip"]) == {"get"}
    assert set(paths["/api/dummy-load/calibration"]) == {"get"}
    assert set(paths["/api/contribution/auth"]) == {"get", "put", "delete"}
    assert set(paths["/api/contribution/auth/device"]) == {"post"}
    assert set(paths["/api/contribution/auth/device/{flow_id}"]) == {"post"}
    assert set(paths["/api/contribution/status"]) == {"get"}

    snapshot_ref = {"$ref": "#/components/schemas/SessionSnapshotResponse"}
    assert paths["/api/sessions"]["post"]["responses"]["201"]["content"]["application/json"]["schema"] == snapshot_ref
    for path, method, status in (
        ("/api/sessions/{session_id}", "get", "200"),
        ("/api/sessions/{session_id}/cancel", "post", "202"),
        ("/api/sessions/{session_id}/confirm", "post", "200"),
        ("/api/sessions/{session_id}/resume", "post", "200"),
    ):
        assert paths[path][method]["responses"][status]["content"]["application/json"]["schema"] == snapshot_ref

    snapshot_schema = contract["components"]["schemas"]["SessionSnapshotResponse"]
    assert set(snapshot_schema["required"]) == set(snapshot_schema["properties"])
    assert snapshot_schema["properties"]["operating_point"] == {
        "anyOf": [{"$ref": "#/components/schemas/OperatingPoint"}, {"type": "null"}],
    }
    assert contract["components"]["schemas"]["AppPowerMeterType"]["enum"] == ["hass", "shelly", "kasa", "dummy"]
