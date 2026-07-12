from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from measure.api import create_app
from measure.coordinator import MeasurementCoordinator
from measure.request import LightMeasurementRequest
from measure.runner.runner import RunnerResult
from measure.session import SessionControl, SessionSnapshot, SessionState
from measure.storage import SessionStorage
import pytest


def entity(entity_id: str, state: str, **attributes: Any) -> SimpleNamespace:  # noqa: ANN401
    return SimpleNamespace(
        entity_id=entity_id,
        state=SimpleNamespace(state=state, attributes=attributes),
    )


class FakeClient:
    def get_entities(self) -> dict[str, SimpleNamespace]:
        return {
            "light": SimpleNamespace(
                entities={
                    "test": entity(
                        "light.test",
                        "on",
                        friendly_name="Test light",
                        supported_color_modes=["brightness", "color_temp", "hs"],
                    ),
                    "switch_like": entity(
                        "light.switch_like",
                        "on",
                        friendly_name="Switch-like light",
                        supported_color_modes=["onoff"],
                    ),
                },
            ),
            "sensor": SimpleNamespace(
                entities={
                    "power": entity("sensor.test_power", "4.2", friendly_name="Test power", unit_of_measurement="W"),
                    "voltage": entity(
                        "sensor.test_voltage",
                        "230",
                        friendly_name="Test voltage",
                        unit_of_measurement="V",
                    ),
                    "temperature": entity("sensor.temperature", "20", unit_of_measurement="°C"),
                    "unknown_power": entity("sensor.unknown_power", "unknown", unit_of_measurement="W"),
                    "text_power": entity("sensor.text_power", "nope", unit_of_measurement="W"),
                },
            ),
        }


class CompletingService:
    def run(
        self,
        request: LightMeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> tuple[RunnerResult, Path]:
        directory = output_root / request.model_id
        directory.mkdir(parents=True)
        (directory / "brightness.csv").write_text("bri,watt\n1,1.0\n", encoding="utf-8")
        control.progress(completed=1, total=1, mode="brightness", estimated_remaining="0s")
        return RunnerResult(model_json_data={}), directory


def payload() -> dict[str, object]:
    return {
        "model_id": "LCT010",
        "product_name": "Test light",
        "measure_device": "Test meter",
        "light_entity_id": "light.test",
        "power_entity_id": "sensor.test_power",
        "voltage_entity_id": "sensor.test_voltage",
        "modes": ["brightness"],
        "generate_model": True,
        "gzip": False,
        "multiple_light_count": 1,
        "sleep_time": 0,
        "sample_count": 1,
        "brightness_step": 5,
        "hue_step": 10,
        "saturation_step": 10,
        "color_temp_step": 5,
        "resume_policy": "new",
    }


def client(tmp_path: Path, *, trusted_ingress_only: bool = False) -> TestClient:
    app = create_app(
        data_root=tmp_path,
        hass_token="test-token",  # noqa: S106
        trusted_ingress_only=trusted_ingress_only,
    )
    app.state.context.client = FakeClient
    app.state.context.coordinator = MeasurementCoordinator(SessionStorage(tmp_path), CompletingService)
    return TestClient(app)


def test_capabilities_and_entity_filters(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    capabilities = test_client.get("/api/capabilities")
    powers = test_client.get("/api/entities?kind=power")
    lights = test_client.get("/api/entities?domain=light")

    assert capabilities.status_code == 200
    assert capabilities.json()["modes"] == ["brightness", "color_temp", "hs"]
    assert [item["entity_id"] for item in powers.json()] == ["sensor.test_power"]
    assert "light.switch_like" not in {item["entity_id"] for item in lights.json()}


def test_preflight_rejects_unavailable_entity(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    response = test_client.post("/api/preflight", json=payload() | {"power_entity_id": "sensor.missing"})

    assert response.status_code == 422
    assert response.json()["code"] == "preflight_failed"


@pytest.mark.parametrize("entity_id", ["sensor.unknown_power", "sensor.text_power"])
def test_preflight_rejects_non_numeric_power_state(tmp_path: Path, entity_id: str) -> None:
    response = client(tmp_path).post("/api/preflight", json=payload() | {"power_entity_id": entity_id})

    assert response.status_code == 422


def test_preflight_rejects_active_session(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    coordinator = test_client.app.state.context.coordinator
    now = "2026-07-12T12:00:00Z"
    coordinator._snapshot = SessionSnapshot(id="active", state=SessionState.RUNNING, created_at=now, updated_at=now)  # noqa: SLF001

    response = test_client.post("/api/preflight", json=payload())

    assert response.status_code == 409


def test_session_lifecycle_and_file_download(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    response = test_client.post("/api/sessions", json=payload())

    assert response.status_code == 201
    current = test_client.get("/api/session/current")
    assert current.status_code == 200
    assert current.json()["progress"]["estimated_remaining_seconds"] == 0
    files = test_client.get("/api/session/current/files")
    assert files.json()[0]["name"] == "LCT010/brightness.csv"
    download = test_client.get("/api/session/current/files/LCT010/brightness.csv")
    assert download.status_code == 200


def test_validation_errors_have_stable_shape(tmp_path: Path) -> None:
    response = client(tmp_path).post("/api/preflight", json=payload() | {"model_id": "../secret"})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert response.json()["field"] == "model_id"


def test_openapi_contract_contains_the_supported_app_endpoints(tmp_path: Path) -> None:
    app = create_app(data_root=tmp_path, hass_token="test-token", trusted_ingress_only=False)  # noqa: S106

    paths = app.openapi()["paths"]

    assert set(paths["/api/sessions"]) == {"post"}
    assert set(paths["/api/session/current"]) == {"get", "delete"}
    assert set(paths["/api/session/current/resume"]) == {"post"}
    assert set(paths["/api/session/current/files/{name}"]) == {"get"}


def test_preflight_rejects_unwritable_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_writability(_: SessionStorage) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(SessionStorage, "verify_writable", fail_writability)

    response = client(tmp_path).post("/api/preflight", json=payload())

    assert response.status_code == 422
    assert response.json()["message"] == "Persistent app storage is not writable"


def test_trusted_ingress_mode_rejects_other_source(tmp_path: Path) -> None:
    response = client(tmp_path, trusted_ingress_only=True).get("/api/capabilities")

    assert response.status_code == 403
    assert response.json()["code"] == "ingress_required"
