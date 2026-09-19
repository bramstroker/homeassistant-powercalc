from dataclasses import replace
from pathlib import Path
import time
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from measure.ha_app.api import create_app
from measure.ha_app.session import SessionSnapshot, SessionState
from measure.ha_app.storage import SessionStorage
from measure.home_assistant.client import HomeAssistantManager
import pytest

from tests.ha_app.api_test_support import (
    AppClientFactory,
    payload,
)


def test_plot_endpoint_rejects_active_session(app_client: TestClient) -> None:
    coordinator = app_client.app.state.context.coordinator
    now = "2026-07-12T12:00:00Z"
    coordinator._snapshot = SessionSnapshot(id="active", state=SessionState.RUNNING, created_at=now, updated_at=now)  # noqa: SLF001

    response = app_client.get("/api/sessions/active/plots")

    assert response.status_code == 409


def test_plot_endpoint_marks_terminal_incomplete_session_as_partial(app_client: TestClient) -> None:
    assert app_client.post("/api/sessions", json=payload()).status_code == 201
    coordinator = app_client.app.state.context.coordinator
    assert coordinator._worker is not None  # noqa: SLF001
    coordinator._worker.join(timeout=5)  # noqa: SLF001
    assert coordinator.current is not None
    assert coordinator.current.state is SessionState.COMPLETED
    coordinator._snapshot = replace(coordinator.current, state=SessionState.CANCELLED)  # noqa: SLF001

    response = app_client.get(f"/api/sessions/{coordinator.current.id}/plots")

    assert response.status_code == 200
    assert response.json()["partial"] is True
    assert response.json()["plots"][0]["id"] == "brightness"


def test_preflight_rejects_unwritable_storage(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_writability(_: SessionStorage) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(SessionStorage, "verify_writable", fail_writability)

    response = app_client.post("/api/preflight", json=payload())

    assert response.status_code == 422
    assert response.json()["message"] == "Persistent app storage is not writable"


def test_trusted_ingress_mode_rejects_other_source(app_client_factory: AppClientFactory) -> None:
    response = app_client_factory(trusted_ingress_only=True).get("/api/capabilities")

    assert response.status_code == 403
    assert response.json()["code"] == "ingress_required"


@pytest.mark.parametrize(
    "trusted_ingress_only,source,expected_status",
    [
        (None, "198.51.100.10", 403),
        (None, "127.0.0.1", 403),
        (None, "172.30.32.2", 200),
        (True, "172.30.32.2", 200),
        (True, "::1", 403),
        (False, "127.0.0.1", 200),
        (False, "::1", 200),
        (False, "198.51.100.10", 403),
        (False, "172.30.32.2", 403),
        (False, "localhost", 403),
        (False, None, 403),
    ],
)
def test_settings_access_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trusted_ingress_only: bool | None,
    source: str | None,
    expected_status: int,
) -> None:
    monkeypatch.delenv("MEASURE_TRUSTED_INGRESS_ONLY", raising=False)
    app = create_app(
        data_root=tmp_path,
        hass_token="test-token",  # noqa: S106
        trusted_ingress_only=trusted_ingress_only,
    )
    test_client = TestClient(app, client=(source, 50000) if source else None)

    assert test_client.get("/api/settings").status_code == expected_status
    response = test_client.put("/api/settings", json={"default_measure_device": "Test meter"})
    assert response.status_code == expected_status


@pytest.mark.parametrize("setting", [None, "true", "false", "", "invalid"])
@pytest.mark.parametrize("path", ["/", "/openapi.json", "/api/settings", "/api/sessions", "/api/contribution/auth"])
def test_external_requests_cannot_disable_access_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    setting: str | None,
    path: str,
) -> None:
    if setting is None:
        monkeypatch.delenv("MEASURE_TRUSTED_INGRESS_ONLY", raising=False)
    else:
        monkeypatch.setenv("MEASURE_TRUSTED_INGRESS_ONLY", setting)
    app = create_app(data_root=tmp_path, hass_token="test-token")  # noqa: S106
    test_client = TestClient(app, client=("198.51.100.10", 50000))

    response = test_client.get(
        path,
        headers={"X-Forwarded-For": "172.30.32.2", "X-Real-IP": "127.0.0.1"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == ("local_access_required" if setting == "false" else "ingress_required")


def test_health_endpoint_for_container_healthcheck(app_client: TestClient) -> None:
    response = app_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_bypasses_ingress_source_check(app_client_factory: AppClientFactory) -> None:
    response = app_client_factory(trusted_ingress_only=True).get("/health")

    assert response.status_code == 200


def test_settings_default_and_update(app_client: TestClient) -> None:

    assert app_client.get("/api/settings").json() == {
        "default_power_entity_id": None,
        "default_measure_device": None,
        "default_measure_device_firmware": None,
        "default_contributor_name": None,
        "default_contributor_github": None,
        "default_contributor_email": None,
        "power_meter": "hass",
        "shelly_ip": None,
        "shelly_username": "admin",
        "shelly_password_configured": False,
        "kasa_ip": None,
        "tapo_credentials_configured": False,
        "fast_test_mode": False,
        "measurement_defaults": {
            "sleep_time": 2.0,
            "sample_count": 1,
            "sleep_time_sample": 1,
            "max_retries": 5,
            "max_nudges": 0,
        },
    }

    updated = app_client.put(
        "/api/settings",
        json={
            "default_power_entity_id": "sensor.test_power",
            "default_measure_device": "Shelly Plug S",
            "default_measure_device_firmware": "1.2.3",
            "default_contributor_name": "Test User",
            "default_contributor_github": "test-user",
            "default_contributor_email": "test@example.com",
            "measurement_defaults": {
                "sleep_time": 3.5,
                "sample_count": 4,
                "sleep_time_sample": 2,
                "max_retries": 8,
                "max_nudges": 1,
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["default_power_entity_id"] == "sensor.test_power"
    assert updated.json()["default_measure_device"] == "Shelly Plug S"
    assert updated.json()["default_measure_device_firmware"] == "1.2.3"
    assert updated.json()["default_contributor_github"] == "test-user"

    reloaded = app_client.get("/api/settings").json()
    assert reloaded["default_power_entity_id"] == "sensor.test_power"
    assert reloaded["default_measure_device"] == "Shelly Plug S"
    assert reloaded["default_contributor_name"] == "Test User"
    assert reloaded["kasa_ip"] is None
    assert reloaded["measurement_defaults"]["sample_count"] == 4
    effective_defaults = app_client.get("/api/capabilities").json()["defaults"]
    assert effective_defaults["sample_count"] == 4
    assert effective_defaults["sleep_time"] == pytest.approx(3.5)


def test_settings_store_shelly_password_separately_and_never_return_it(app_client: TestClient, tmp_path: Path) -> None:
    payload = {
        "power_meter": "shelly",
        "shelly_ip": "192.0.2.30",
        "shelly_username": "measurement",
        "shelly_password": "device-password",
    }

    saved = app_client.put("/api/settings", json=payload)

    assert saved.status_code == 200
    assert saved.json()["shelly_password_configured"] is True
    assert "shelly_password" not in saved.json()
    assert "device-password" not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert (tmp_path / "shelly_credentials.json").stat().st_mode & 0o777 == 0o600

    preserved = app_client.put("/api/settings", json=payload | {"shelly_password": None})
    assert preserved.json()["shelly_password_configured"] is True
    assert "device-password" not in app_client.get("/api/settings").text

    cleared = app_client.put("/api/settings", json=payload | {"shelly_password": None, "clear_shelly_password": True})
    assert cleared.json()["shelly_password_configured"] is False
    assert not (tmp_path / "shelly_credentials.json").exists()


def test_fast_test_mode_requires_developer_mode_and_dummy_adapters(app_client_factory: AppClientFactory) -> None:
    regular_client = app_client_factory()
    rejected = regular_client.put("/api/settings", json={"fast_test_mode": True})

    assert rejected.status_code == 400
    assert rejected.json()["message"] == "Fast test mode requires developer mode"

    developer_client = app_client_factory(developer_mode=True)
    assert developer_client.put("/api/settings", json={"fast_test_mode": True}).status_code == 200
    assert developer_client.get("/api/capabilities").json()["fast_test_mode"] is True

    dummy_request = payload() | {
        "controller": {"type": "dummy"},
        "power_meter": {"type": "dummy"},
    }
    started = developer_client.post("/api/sessions", json=dummy_request)

    assert started.status_code == 201
    prepared = started.json()["request"]
    assert prepared["fast_test_mode"] is True
    assert prepared["parameters"]["fast_test_mode"] is True
    assert prepared["parameters"]["sleep_time"] == 0
    assert prepared["parameters"]["sleep_initial"] == 0
    assert prepared["parameters"]["sleep_standby"] == 0


def test_default_app_runs_a_synthetic_light_measurement_and_exports_its_profile(tmp_path: Path) -> None:
    app = create_app(
        data_root=tmp_path,
        hass_token="test-token",  # noqa: S106
        trusted_ingress_only=False,
        developer_mode=True,
    )
    app.state.context.home_assistant.close()
    app.state.context.home_assistant = MagicMock(spec=HomeAssistantManager, token="test-token")  # noqa: S106
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        assert test_client.put("/api/settings", json={"fast_test_mode": True}).status_code == 200
        request = payload() | {
            "controller": {"type": "dummy"},
            "power_meter": {"type": "dummy"},
            "parameters": payload()["parameters"] | {"bri_bri_steps": 255},  # type: ignore[operator]
        }
        started = test_client.post("/api/sessions", json=request)
        assert started.status_code == 201
        session_id = started.json()["session_id"]

        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                snapshot = test_client.get(f"/api/sessions/{session_id}").json()
                if snapshot["state"] == "awaiting_confirmation":
                    assert test_client.post(f"/api/sessions/{session_id}/confirm").status_code == 200
                elif snapshot["state"] in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(0.01)

            assert snapshot["state"] == "completed", snapshot
            files = test_client.get(f"/api/sessions/{session_id}/files").json()
            assert {file["name"] for file in files} >= {"LCT010/brightness.csv", "LCT010/model.json"}
            measurements = test_client.get(f"/api/sessions/{session_id}/files/LCT010/brightness.csv")
            assert measurements.status_code == 200
            assert len(measurements.text.splitlines()) >= 2
            model = test_client.get(f"/api/sessions/{session_id}/files/LCT010/model.json")
            assert model.status_code == 200
            assert model.json()["calculation_strategy"] == "lut"
            assert model.json()["device_type"] == "light"
        finally:
            if app.state.context.coordinator.current.state in {
                SessionState.RUNNING,
                SessionState.AWAITING_CONFIRMATION,
                SessionState.CANCELLING,
            }:
                test_client.post(f"/api/sessions/{session_id}/cancel")


def test_fast_test_mode_does_not_modify_real_measurement_requests(app_client_factory: AppClientFactory) -> None:
    test_client = app_client_factory(developer_mode=True)
    assert test_client.put("/api/settings", json={"fast_test_mode": True}).status_code == 200

    request = payload() | {
        "fast_test_mode": True,
        "parameters": payload()["parameters"] | {"sleep_time": 7},  # type: ignore[operator]
    }
    response = test_client.post("/api/preflight", json=request)

    assert response.status_code == 200
    started = test_client.post("/api/sessions", json=request)
    assert started.status_code == 201
    assert started.json()["request"]["fast_test_mode"] is False
    assert started.json()["request"]["parameters"]["fast_test_mode"] is False
    assert started.json()["request"]["parameters"]["sleep_time"] == 7


def test_settings_rejects_invalid_entity(app_client: TestClient) -> None:
    response = app_client.put("/api/settings", json={"default_power_entity_id": "not-an-entity"})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_settings_rejects_invalid_measurement_defaults(app_client: TestClient) -> None:
    response = app_client.put("/api/settings", json={"measurement_defaults": {"max_nudges": 21}})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
