from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from measure.const import MeasureType
from measure.contribution.github import GitHubUser
from measure.ha_app.contribution.coordinator import ContributionApiCoordinator
from measure.ha_app.contribution.models import (
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionPreviewResponse,
    ContributionState,
    ContributionSubmissionResult,
)
from measure.ha_app.contribution.service import SharedContributionService
from measure.ha_app.coordinator import (
    MeasurementCoordinator,
)
from measure.ha_app.session import SessionState
from measure.ha_app.storage import SessionStorage
from measure.request import MeasurementRequest
from pydantic import SecretStr, TypeAdapter
import pytest

from tests.ha_app.api_test_support import (
    FakeContributionService,
    SummaryService,
    payload,
)


def test_contribution_disconnect_clears_authentication(app_client: TestClient) -> None:
    context = app_client.app.state.context
    service = FakeContributionService()
    context.contribution = ContributionApiCoordinator(context.storage, service_factory=lambda: service)
    connected = app_client.put("/api/contribution/auth", json={"token": "github-test-token"})
    assert connected.status_code == 200
    assert connected.json()["authenticated"] is True

    response = app_client.delete("/api/contribution/auth")

    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    assert response.json()["username"] is None
    assert app_client.get("/api/contribution/auth").json()["authenticated"] is False


def test_contribution_device_flow_reports_configuration_and_uses_injected_service(
    app_client: TestClient,
) -> None:
    unavailable = app_client.post("/api/contribution/auth/device")
    assert unavailable.status_code == 401
    assert unavailable.json()["code"] == "auth_unavailable"
    assert app_client.get("/api/contribution/auth").json()["device_flow_available"] is False

    service = FakeContributionService()
    context = app_client.app.state.context
    context.contribution = ContributionApiCoordinator(
        context.storage,
        service_factory=lambda: service,
        oauth_client_id="client-1",
    )

    started = app_client.post("/api/contribution/auth/device")
    assert started.status_code == 200
    assert "device_code" not in started.json()
    flow_id = started.json()["flow_id"]

    polled = app_client.post(f"/api/contribution/auth/device/{flow_id}")
    assert polled.status_code == 200
    assert polled.json()["status"] == "authorized"
    assert polled.json()["auth"]["authenticated"] is True
    assert polled.json()["auth"]["username"] == "oauth-user"
    assert polled.json()["auth"]["device_flow_available"] is True

    unknown = app_client.post("/api/contribution/auth/device/unknown-flow")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "flow_not_found"
    completed = app_client.post(f"/api/contribution/auth/device/{flow_id}")
    assert completed.status_code == 404


@pytest.mark.parametrize(
    "integrations, expected",
    [
        ({"light.one": "hue", "light.two": "hue"}, "hue"),
        ({"light.one": "hue", "light.two": "zha"}, None),
        ({"light.one": "hue", "light.two": None}, None),
    ],
)
def test_contribution_integration_requires_every_light_to_share_the_integration(
    tmp_path: Path,
    integrations: dict[str, str | None],
    expected: str | None,
) -> None:
    request_payload = payload()
    request_payload["controller"] = {
        "type": "hass_multi",
        "entity_ids": ["light.one", "light.two"],
    }
    request = TypeAdapter(MeasurementRequest).validate_python(request_payload)
    coordinator = ContributionApiCoordinator(
        SessionStorage(tmp_path),
        resolve_integration=lambda entity_ids: {entity_id: integrations.get(entity_id) for entity_id in entity_ids},
    )

    assert coordinator._integration(request) == expected  # noqa: SLF001


def test_contribution_pat_rejects_reported_insufficient_scope(tmp_path: Path) -> None:
    github = MagicMock()
    github.fetch_authenticated_user.return_value = GitHubUser(
        login="measure-user",
        scopes=("read:user",),
        scopes_reported=True,
    )
    service = SharedContributionService(tmp_path)
    token = SecretStr("github_pat_test")
    with (
        patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github),
        pytest.raises(ContributionApiError, match="must grant public repository and workflow access"),
    ):
        service.connect_pat(token)


def test_contribution_device_flow_records_granted_scopes_without_claiming_verified(tmp_path: Path) -> None:
    github = MagicMock()
    github.poll_device_flow.return_value = {"access_token": "gho_test", "scope": "public_repo"}
    github.fetch_authenticated_user.return_value = GitHubUser(
        login="oauth-user",
        scopes=("public_repo",),
        scopes_reported=True,
    )
    with patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github):
        service = SharedContributionService(tmp_path)
        polled = service.poll_device_flow("client-id", "device-code")
        status = service.auth_status()

    assert polled.status == "authorized"
    assert status.scopes == ["public_repo"]
    assert status.permissions_verified is False


@pytest.mark.parametrize("interval", [7, "7"])
def test_contribution_device_flow_slow_down_reports_retry_after(tmp_path: Path, interval: int | str) -> None:
    github = MagicMock()
    github.poll_device_flow.return_value = {
        "error": "slow_down",
        "error_description": "Slow down",
        "interval": interval,
    }

    with patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github):
        polled = SharedContributionService(tmp_path).poll_device_flow("client-id", "device-code")

    assert polled.status == "slow_down"
    assert polled.message == "Slow down"
    assert polled.retry_after == 7


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "authorization_pending"},
        {"error": "slow_down"},
        {"error": "slow_down", "interval": 0},
        {"error": "slow_down", "interval": "soon"},
    ],
)
def test_contribution_device_flow_pending_or_invalid_slow_down_has_no_retry_after(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    github = MagicMock()
    github.poll_device_flow.return_value = payload

    with patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github):
        polled = SharedContributionService(tmp_path).poll_device_flow("client-id", "device-code")

    assert polled.status == ("slow_down" if payload["error"] == "slow_down" else "pending")
    assert polled.retry_after is None


def test_measurement_can_complete_without_product_identity(app_client: TestClient) -> None:
    context = app_client.app.state.context
    context.contribution = ContributionApiCoordinator(
        context.storage,
        service_factory=FakeContributionService,
        resolve_model_id=context.get_entity_model_ids,
    )
    request = payload() | {"model_id": "", "product_name": "", "session_name": "Desk lamp"}
    started = app_client.post("/api/sessions", json=request)
    assert started.status_code == 201
    session_id = started.json()["session_id"]
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001
    assert context.storage.load_snapshot(session_id).state == SessionState.COMPLETED
    assert (context.storage.artifact_directory(session_id, "") / "brightness.csv").is_file()
    sessions = app_client.get("/api/sessions").json()
    assert sessions[0]["product_name"] == "Desk lamp"
    draft = app_client.get(f"/api/sessions/{session_id}/contribution")
    assert draft.status_code == 200
    assert draft.json()["model_id"] == "Hue White Ambiance"
    assert draft.json()["product_name"] == ""


def test_initial_contribution_draft_includes_detected_connectivity(app_client: TestClient) -> None:
    context = app_client.app.state.context
    started = app_client.post("/api/sessions", json=payload())
    assert started.status_code == 201
    session_id = started.json()["session_id"]
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001
    devices = [{"id": "light-device", "connections": [["mac", "00:17:88:01:02:03:04:05"]], "via_device_id": "bridge"}]
    with patch.object(context.home_assistant, "get_device_registry", return_value=devices):
        draft = app_client.get(f"/api/sessions/{session_id}/contribution")

    assert draft.status_code == 200
    assert draft.json()["device_specs"] == {"connectivity": ["zigbee"]}


@pytest.mark.parametrize(
    "preview_details,submitted_details,matches",
    [
        ({}, {"manufacturer_name": "Other"}, False),
        ({}, {"model_id": "Other"}, False),
        ({}, {"product_name": "Other"}, False),
        ({}, {"contributor": "Other"}, False),
        ({}, {"contributor_github": "octo"}, False),
        ({}, {"contributor_email": "octo@example.com"}, False),
        ({}, {"aliases": ["Other"]}, False),
        ({}, {"gtins": ["8719514340105"]}, False),
        ({}, {"product_url": "https://example.com"}, False),
        ({}, {"mains_voltage": 230}, False),
        ({}, {"device_specs": {"power": 10}}, False),
        ({}, {"measure_device": "Meter"}, False),
        ({}, {"measure_device_firmware": "1.0"}, False),
        ({}, {"measure_description": "Test run"}, False),
        ({}, {"notes": "Changed"}, False),
        ({}, {}, True),
        (
            {},
            {
                "contributor_github": "",
                "contributor_email": "",
                "product_url": "",
                "measure_device": "",
                "measure_device_firmware": "",
                "measure_description": "",
            },
            True,
        ),
        ({"aliases": ["A", "B"]}, {"aliases": ["B", "A"]}, False),
        (
            {"device_specs": {"power": 10, "nested": {"a": 1, "b": 2}}},
            {"device_specs": {"nested": {"b": 2, "a": 1}, "power": 10}},
            True,
        ),
        ({"device_specs": {"value": 1}}, {"device_specs": {"value": True}}, False),
        ({"device_specs": {"value": 1}}, {"device_specs": {"value": 1.0}}, False),
        ({"device_specs": {}}, {"device_specs": None}, False),
    ],
)
def test_contribution_submission_must_match_preview(
    app_client: TestClient,
    preview_details: dict[str, object],
    submitted_details: dict[str, object],
    matches: bool,
) -> None:
    service = FakeContributionService()
    service.username = "measure-user"
    context = app_client.app.state.context
    context.contribution = ContributionApiCoordinator(context.storage, service_factory=lambda: service)
    started = app_client.post("/api/sessions", json=payload())
    session_id = started.json()["session_id"]
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001
    metadata = {
        "manufacturer_name": "Signify",
        "model_id": "LCT010",
        "product_name": "Test light",
        "contributor": "measure-user",
    }
    endpoint = f"/api/sessions/{session_id}/contribution"
    preview = app_client.post(f"{endpoint}/preview", json=metadata | preview_details)
    assert preview.status_code == 200

    submitted = app_client.post(endpoint, json=metadata | submitted_details | {"confirmed": True})

    assert submitted.status_code == (200 if matches else 409)
    assert service.submit_calls == int(matches)
    if not matches:
        assert submitted.json()["code"] == "preview_required"


@pytest.mark.parametrize(
    "failure,expected_code,expected_status",
    [
        (RuntimeError("GitHub unavailable"), ContributionApiErrorCode.SUBMISSION_FAILED, 502),
        (
            ContributionApiError(ContributionApiErrorCode.INVALID_METADATA, "Invalid profile"),
            ContributionApiErrorCode.INVALID_METADATA,
            422,
        ),
    ],
)
def test_failed_contribution_is_persisted_and_can_be_retried(
    app_client: TestClient,
    tmp_path: Path,
    failure: Exception,
    expected_code: ContributionApiErrorCode,
    expected_status: int,
) -> None:
    service = FakeContributionService()
    service.username = "measure-user"
    context = app_client.app.state.context
    context.contribution = ContributionApiCoordinator(context.storage, service_factory=lambda: service)
    started = app_client.post("/api/sessions", json=payload())
    session_id = started.json()["session_id"]
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001
    metadata = {
        "manufacturer_name": "Signify",
        "model_id": "LCT010",
        "product_name": "Test light",
        "contributor": "measure-user",
    }
    endpoint = f"/api/sessions/{session_id}/contribution"
    assert app_client.post(f"{endpoint}/preview", json=metadata).status_code == 200

    with patch.object(service, "submit", side_effect=failure):
        submitted = app_client.post(endpoint, json=metadata | {"confirmed": True})

    assert submitted.status_code == expected_status
    assert submitted.json()["code"] == expected_code
    status = app_client.get("/api/contribution/status").json()
    assert status["state"] == ContributionState.FAILED
    assert status["error"] == str(failure)
    assert status["preview"] is not None
    context.contribution = ContributionApiCoordinator(SessionStorage(tmp_path), service_factory=lambda: service)
    assert context.contribution.status().state == ContributionState.FAILED

    retried = app_client.post(endpoint, json=metadata | {"confirmed": True})

    assert retried.status_code == 200
    assert service.submit_calls == 1
    status = app_client.get("/api/contribution/status").json()
    assert status["state"] == ContributionState.SUBMITTED
    assert status["error"] is None


@pytest.mark.parametrize(
    "authenticated,has_preview,expected_status,expected_code",
    [
        (False, True, 401, "auth_unavailable"),
        (True, False, 409, "preview_required"),
    ],
)
def test_contribution_submission_requires_authentication_and_preview(
    app_client: TestClient,
    authenticated: bool,
    has_preview: bool,
    expected_status: int,
    expected_code: str,
) -> None:
    service = FakeContributionService()
    service.username = "measure-user"
    context = app_client.app.state.context
    context.contribution = ContributionApiCoordinator(context.storage, service_factory=lambda: service)
    started = app_client.post("/api/sessions", json=payload())
    session_id = started.json()["session_id"]
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001
    metadata = {
        "manufacturer_name": "Signify",
        "model_id": "LCT010",
        "product_name": "Test light",
        "contributor": "measure-user",
    }
    endpoint = f"/api/sessions/{session_id}/contribution"
    if has_preview:
        assert app_client.post(f"{endpoint}/preview", json=metadata).status_code == 200
    if not authenticated:
        service.disconnect()
    previous_status = context.contribution.status()

    response = app_client.post(endpoint, json=metadata | {"confirmed": True})

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
    assert service.submit_calls == 0
    assert context.contribution.status() == previous_status


def test_concurrent_contribution_submission_is_rejected(app_client: TestClient) -> None:
    service = FakeContributionService()
    service.username = "measure-user"
    context = app_client.app.state.context
    context.contribution = ContributionApiCoordinator(context.storage, service_factory=lambda: service)
    started = app_client.post("/api/sessions", json=payload())
    session_id = started.json()["session_id"]
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001
    metadata = {
        "manufacturer_name": "Signify",
        "model_id": "LCT010",
        "product_name": "Test light",
        "contributor": "measure-user",
    }
    endpoint = f"/api/sessions/{session_id}/contribution"
    assert app_client.post(f"{endpoint}/preview", json=metadata).status_code == 200
    entered = Event()
    release = Event()

    def submit(*, preview: ContributionPreviewResponse, artifact_root: Path) -> ContributionSubmissionResult:
        assert preview.session_id == session_id
        assert artifact_root.is_dir()
        entered.set()
        assert release.wait(timeout=5)
        return ContributionSubmissionResult(pull_request_url="https://github.test/pr/1", message="Submitted")

    with patch.object(service, "submit", side_effect=submit) as submission, ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(app_client.post, endpoint, json=metadata | {"confirmed": True})
        try:
            assert entered.wait(timeout=5)
            assert context.storage.load_contribution_status().state is ContributionState.SUBMITTING

            rejected = app_client.post(endpoint, json=metadata | {"confirmed": True})

            assert rejected.status_code == 409
            assert rejected.json()["code"] == "contribution_active"
            assert submission.call_count == 1
            assert context.contribution.status().state is ContributionState.SUBMITTING
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 200

    assert context.storage.load_contribution_status().state is ContributionState.SUBMITTED


def test_contribution_preview_submit_and_artifact_lock(
    app_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POWERCALC_GITHUB_REPOSITORY", "test-owner/powercalc-sandbox")
    monkeypatch.setenv("POWERCALC_GITHUB_BRANCH", "main")
    service = FakeContributionService()
    context = app_client.app.state.context
    context.contribution = ContributionApiCoordinator(
        context.storage,
        service_factory=lambda: service,
        resolve_integration=context.get_entity_integrations,
        resolve_manufacturer=lambda entity_ids: dict.fromkeys(entity_ids, "Signify"),
    )

    started = app_client.post("/api/sessions", json=payload())
    assert started.status_code == 201
    session_id = started.json()["session_id"]
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001

    auth = app_client.put("/api/contribution/auth", json={"token": "github_pat_test"})
    assert auth.status_code == 200
    assert auth.json()["authenticated"] is True
    assert auth.json()["username"] == "measure-user"
    settings_path = tmp_path / "settings.json"
    if settings_path.exists():
        assert "github_pat_test" not in settings_path.read_text(encoding="utf-8")
    assert (
        app_client.put(
            "/api/settings",
            json={
                "default_measure_device_firmware": "1.2.3",
                "default_contributor_name": "Test User",
                "default_contributor_github": "test-user",
                "default_contributor_email": "test@example.com",
            },
        ).status_code
        == 200
    )

    draft = app_client.get(f"/api/sessions/{session_id}/contribution")
    assert draft.status_code == 200
    assert draft.json()["eligible"] is False
    assert draft.json()["repository"] == "test-owner/powercalc-sandbox"
    assert draft.json()["base_branch"] == "main"
    assert draft.json()["home_assistant"]["integration"] == "hue"
    assert draft.json()["manufacturer_name"] == "Signify"
    assert draft.json()["measure_device_firmware"] == "1.2.3"
    assert draft.json()["contributor"] == "Test User"
    assert draft.json()["contributor_github"] == "test-user"
    assert draft.json()["contributor_email"] == "test@example.com"
    assert "- Integration: hue" in draft.json()["pr_body"]

    preview = app_client.post(
        f"/api/sessions/{session_id}/contribution/preview",
        json={
            "manufacturer_name": "Signify",
            "model_id": "LCT010",
            "product_name": "Test light",
            "contributor": "measure-user",
            "notes": "No aliases.",
        },
    )
    assert preview.status_code == 200
    assert preview.json()["pr_title"] == "Add signify LCT010 power profile"
    assert preview.json()["files"][0]["path"] == "profile_library/signify/LCT010/model.json"
    assert preview.json()["notes"] == "No aliases."
    assert preview.json()["home_assistant"]["integration"] == "hue"
    assert service.preview_calls == 1
    assert service.submit_calls == 0

    archive = app_client.get(f"/api/sessions/{session_id}/contribution/job-1/profile.zip")
    assert archive.status_code == 200
    assert archive.content == b"PK\x03\x04prepared-profile"
    assert archive.headers["content-type"] == "application/zip"
    assert archive.headers["content-disposition"] == 'attachment; filename="powercalc-profile.zip"'

    stale_archive = app_client.get(f"/api/sessions/{session_id}/contribution/stale-job/profile.zip")
    assert stale_archive.status_code == 409
    assert stale_archive.json()["code"] == "preview_required"

    unconfirmed = app_client.post(
        f"/api/sessions/{session_id}/contribution",
        json={
            "manufacturer_name": "Signify",
            "model_id": "LCT010",
            "product_name": "Test light",
            "contributor": "measure-user",
            "notes": "No aliases.",
            "confirmed": False,
        },
    )
    assert unconfirmed.status_code == 400
    assert service.submit_calls == 0

    submitted = app_client.post(
        f"/api/sessions/{session_id}/contribution",
        json={
            "manufacturer_name": "Signify",
            "model_id": "LCT010",
            "product_name": "Test light",
            "contributor": "measure-user",
            "notes": "No aliases.",
            "confirmed": True,
        },
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "success"
    assert submitted.json()["pull_request_url"] == "https://github.com/example/pull/1"
    assert service.submit_calls == 1

    status = app_client.get("/api/contribution/status")
    assert status.status_code == 200
    assert status.json()["state"] == "submitted"
    assert status.json()["submission_url"] == "https://github.com/example/pull/1"
    assert status.json()["session_id"] == session_id

    files = app_client.get(f"/api/sessions/{session_id}/files").json()
    assert [item["name"] for item in files] == ["LCT010/brightness.csv"]
    diagnostics = app_client.get(f"/api/sessions/{session_id}/diagnostics")
    assert "github_pat_test" not in diagnostics.text


def test_contribution_preview_rejects_unsupported_generated_session(app_client: TestClient) -> None:
    context = app_client.app.state.context
    service = FakeContributionService()
    context.coordinator = MeasurementCoordinator(context.storage, SummaryService)
    context.contribution = ContributionApiCoordinator(context.storage, service_factory=lambda: service)
    run_payload = {
        "measure_type": MeasureType.AVERAGE,
        "model_id": "average-device",
        "power_meter": {"type": "hass", "entity_id": "sensor.test_power"},
        "duration": 1,
        "generate_model": True,
    }
    assert app_client.post("/api/sessions", json=run_payload).status_code == 201
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001
    artifact_root = context.storage.artifact_directory(context.coordinator.current.id, "average-device")
    artifact_root.mkdir(parents=True)
    (artifact_root / "model.json").write_text("{}", encoding="utf-8")

    response = app_client.post(
        f"/api/sessions/{context.coordinator.current.id}/contribution/preview",
        json={
            "manufacturer_name": "Acme",
            "model_id": "average-device",
            "product_name": "Average device",
            "contributor": "measure-user",
            "notes": "",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "artifacts_required"
    assert service.preview_calls == 0
