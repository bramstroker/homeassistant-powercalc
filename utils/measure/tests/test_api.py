from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from measure.const import MeasureType
from measure.execution import LightOperatingPoint
from measure.ha_app.api import create_app
from measure.ha_app.coordinator import MeasurementCoordinator, SessionMeasurementService
from measure.ha_app.session import SessionControl, SessionSnapshot, SessionState
from measure.ha_app.storage import SessionStorage
from measure.home_assistant import HomeAssistantEntityData, HomeAssistantManager
from measure.powermeter.diagnostics import PowerMeterDiagnostics
from measure.request import MeasurementRequest
from measure.runner.runner import RunnerResult
from measure.tuning import MeasurementParameters
import pytest


def entity(entity_id: str, state: str, **attributes: Any) -> SimpleNamespace:  # noqa: ANN401
    return SimpleNamespace(
        entity_id=entity_id,
        state=SimpleNamespace(state=state, attributes=attributes),
    )


class FakeClient:
    def __init__(self) -> None:
        self.state_calls = 0

    def close(self) -> None:
        return None

    async def discover_zeroconf(self, collection_window: float = 2.0) -> tuple[dict[str, object], ...]:
        return ()

    def list_entity_registry(self) -> tuple[SimpleNamespace, ...]:
        return (
            SimpleNamespace(entity_id="sensor.test_power", device_id="meter-device"),
            SimpleNamespace(entity_id="sensor.test_voltage", device_id="meter-device"),
            SimpleNamespace(entity_id="light.test", device_id="light-device"),
        )

    def get_device_registry(self) -> tuple[dict[str, object], ...]:
        return (
            {"id": "meter-device", "model_id": "PM-001", "model": "Power Meter"},
            {"id": "light-device", "model_id": None, "model": "Hue White Ambiance"},
        )

    def get_entities(self) -> dict[str, SimpleNamespace]:
        return {
            "light": SimpleNamespace(
                entities={
                    "test": entity(
                        "light.test",
                        "on",
                        friendly_name="Test light",
                        supported_color_modes=["brightness", "color_temp", "hs"],
                        effect_list=["colorloop"],
                        min_color_temp_kelvin=2202,
                        max_color_temp_kelvin=6535,
                    ),
                    "switch_like": entity(
                        "light.switch_like",
                        "on",
                        friendly_name="Switch-like light",
                        supported_color_modes=["onoff"],
                    ),
                },
            ),
            "fan": SimpleNamespace(
                entities={"fan": entity("fan.test", "on", friendly_name="Test fan")},
            ),
            "media_player": SimpleNamespace(
                entities={"speaker": entity("media_player.test", "playing", friendly_name="Test speaker")},
            ),
            "vacuum": SimpleNamespace(
                entities={"robot": entity("vacuum.test", "docked", friendly_name="Test robot")},
            ),
            "sensor": SimpleNamespace(
                entities={
                    "power": entity(
                        "sensor.test_power",
                        "4.2",
                        friendly_name="Test power",
                        device_class="power",
                        unit_of_measurement="W",
                    ),
                    "voltage": entity(
                        "sensor.test_voltage",
                        "230",
                        friendly_name="Test voltage",
                        device_class="voltage",
                        unit_of_measurement="V",
                    ),
                    "temperature": entity("sensor.temperature", "20", unit_of_measurement="°C"),
                    "unknown_power": entity(
                        "sensor.unknown_power",
                        "unknown",
                        device_class="power",
                        unit_of_measurement="W",
                    ),
                    "text_power": entity("sensor.text_power", "nope", device_class="power", unit_of_measurement="W"),
                    "wrong_device_class": entity(
                        "sensor.wrong_device_class",
                        "4.2",
                        device_class="energy",
                        unit_of_measurement="W",
                    ),
                },
            ),
        }

    def get_entity_data(self) -> HomeAssistantEntityData:
        return HomeAssistantEntityData(
            entities=self.get_entities(),  # type: ignore[arg-type]
            entity_registry=self.list_entity_registry(),  # type: ignore[arg-type]
            device_registry=self.get_device_registry(),
        )

    def get_state(
        self,
        *,
        entity_id: str | None = None,
        group_id: str | None = None,
        slug: str | None = None,
    ) -> SimpleNamespace:
        self.state_calls += 1
        now = datetime.now(UTC)
        return SimpleNamespace(state="4.2", last_reported=now, last_updated=now)


class CompletingService(SessionMeasurementService):
    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> RunnerResult:
        directory = output_root / request.model_id
        directory.mkdir(parents=True)
        (directory / "brightness.csv").write_text("bri,watt\n1,1.0\n", encoding="utf-8")
        control.log("Reading light.test with sensor.test_power")
        control.operating_point(LightOperatingPoint(type="light", on=True, brightness=128))
        control.progress(completed=1, total=1, mode="brightness", estimated_remaining="0s")
        return RunnerResult(model_json_data={})


class SummaryService(SessionMeasurementService):
    def run(
        self,
        request: MeasurementRequest,
        control: SessionControl,
        output_root: Path,
    ) -> RunnerResult:
        control.progress(completed=30, total=30, mode="Averaging", estimated_remaining="0s")
        summary = {"Average power": "42.3 W", "Duration": "30 s"}
        return RunnerResult(model_json_data={}, summary=summary)


def payload() -> dict[str, object]:
    return {
        "measure_type": MeasureType.LIGHT,
        "model_id": "LCT010",
        "product_name": "Test light",
        "measure_device": "Test meter",
        "controller": {"type": "hass", "entity_id": "light.test"},
        "power_meter": {
            "type": "hass",
            "entity_id": "sensor.test_power",
            "voltage_entity_id": "sensor.test_voltage",
        },
        "modes": ["brightness"],
        "generate_model": True,
        "gzip": False,
        "multiple_light_count": 1,
        "parameters": {
            "sleep_time": 0,
            "sample_count": 1,
            "bri_bri_steps": 1,
            "ct_bri_steps": 5,
            "ct_mired_steps": 10,
            "hs_bri_steps": 32,
            "hs_hue_steps": 2731,
            "hs_sat_steps": 32,
        },
        "resume_policy": "new",
    }


def client(tmp_path: Path, *, trusted_ingress_only: bool = False) -> TestClient:
    app = create_app(
        data_root=tmp_path,
        hass_token="test-token",  # noqa: S106
        trusted_ingress_only=trusted_ingress_only,
    )
    app.state.context.home_assistant = FakeClient()
    app.state.context.power_meter_diagnostics = PowerMeterDiagnostics(
        app.state.context.build_power_meter,
        duration=0,
    )
    app.state.context.coordinator = MeasurementCoordinator(SessionStorage(tmp_path), CompletingService)
    return TestClient(app)


def test_capabilities_and_entity_filters(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    capabilities = test_client.get("/api/capabilities")
    powers = test_client.get("/api/entities?device_class=power")
    lights = test_client.get("/api/entities?domain=light")

    assert capabilities.status_code == 200
    assert capabilities.json()["modes"] == ["brightness", "color_temp", "hs", "effect"]
    defaults = MeasurementParameters()
    assert capabilities.json()["defaults"] == {
        "sleep_time": defaults.sleep_time,
        "sample_count": defaults.sample_count,
        "sleep_time_sample": defaults.sleep_time_sample,
        "max_retries": defaults.max_retries,
        "max_nudges": defaults.max_nudges,
        "bri_bri_steps": defaults.bri_bri_steps,
        "ct_bri_steps": defaults.ct_bri_steps,
        "ct_mired_steps": defaults.ct_mired_steps,
        "hs_bri_steps": defaults.hs_bri_steps,
        "hs_hue_steps": defaults.hs_hue_steps,
        "hs_sat_steps": defaults.hs_sat_steps,
        "min_brightness": defaults.min_brightness,
        "sleep_initial": defaults.sleep_initial,
        "sleep_standby": defaults.sleep_standby,
        "effect_bri_steps": defaults.effect_bri_steps,
        "measure_time_effect": defaults.measure_time_effect,
        "measure_time_effect_min": defaults.measure_time_effect_min,
    }
    assert [item["entity_id"] for item in powers.json()] == ["sensor.test_power"]
    assert powers.json()[0]["device_id"] == "meter-device"
    assert powers.json()[0]["model_id"] == "PM-001"
    assert powers.json()[0]["related_voltage_entity_id"] == "sensor.test_voltage"
    assert test_client.get("/api/entities?kind=power").status_code == 400
    assert "light.switch_like" not in {item["entity_id"] for item in lights.json()}
    assert lights.json()[0]["supported_modes"] == ["brightness", "color_temp", "hs", "effect"]
    assert lights.json()[0]["model_id"] == "Hue White Ambiance"
    assert lights.json()[0]["min_mired"] == 153
    assert lights.json()[0]["max_mired"] == 454

    for domain, expected in (("fan", "fan.test"), ("media_player", "media_player.test"), ("vacuum", "vacuum.test")):
        response = test_client.get(f"/api/entities?domain={domain}")
        assert response.status_code == 200, domain
        assert [item["entity_id"] for item in response.json()] == [expected]


def test_app_closes_home_assistant_manager_at_shutdown(tmp_path: Path) -> None:
    app = create_app(data_root=tmp_path, hass_token="test-token", trusted_ingress_only=False)  # noqa: S106
    home_assistant = MagicMock(spec=HomeAssistantManager)
    app.state.context.home_assistant = home_assistant

    with TestClient(app) as test_client:
        assert test_client.get("/api/capabilities").status_code == 200

    home_assistant.close.assert_called_once_with()


def test_power_meter_test_endpoint(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    dummy = test_client.post("/api/settings/test-power-meter", json={"power_meter": "dummy"})
    assert dummy.status_code == 200
    assert dummy.json()["success"] is True
    assert dummy.json()["status"] == "unsupported"

    shelly = test_client.post("/api/settings/test-power-meter", json={"power_meter": "shelly", "shelly_ip": None})
    assert shelly.json()["success"] is False
    assert shelly.json()["message"] == "Enter the Shelly IP address first"

    hass = test_client.post(
        "/api/settings/test-power-meter",
        json={"power_meter": "hass", "default_power_entity_id": None},
    )
    assert hass.json()["success"] is False
    assert "power sensor" in hass.json()["message"].lower()

    validated = test_client.post(
        "/api/settings/test-power-meter",
        json={"power_meter": "hass", "default_power_entity_id": "sensor.test_power"},
    )
    assert validated.json()["success"] is True
    assert validated.json()["precision_decimals"] == 1
    assert validated.json()["update_interval_status"] == "poor"


def test_shelly_discovery_endpoint(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    response = test_client.get("/api/power-meters/shelly")

    assert response.status_code == 200
    assert response.json() == {"devices": [], "available": True, "message": None}


def test_measure_definitions_and_average_request(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    definitions = test_client.get("/api/measure-definitions")
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
    assert fields["charging_device_type"]["options"] == [
        {"value": "vacuum_robot", "label": "Vacuum robot", "entity_domain": "vacuum"},
        {"value": "lawn_mower_robot", "label": "Lawn mower robot", "entity_domain": "lawn_mower"},
    ]

    payload = {
        "measure_type": MeasureType.AVERAGE,
        "power_meter": {"type": "hass", "entity_id": "sensor.test_power"},
        "duration": 60,
    }
    assert test_client.post("/api/preflight", json=payload).status_code == 200
    assert test_client.post("/api/sessions", json=payload).status_code == 201


def test_preflight_exposes_quality_warnings_and_start_reuses_diagnostics(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    home_assistant = test_client.app.state.context.home_assistant

    response = test_client.post("/api/preflight", json=payload())

    assert response.status_code == 200
    assert response.json()["power_meter_diagnostic"]["precision_status"] == "good"
    assert response.json()["power_meter_diagnostic"]["update_interval_status"] == "poor"
    assert "did not report often enough" in response.json()["warnings"][0]
    assert test_client.post("/api/sessions", json=payload()).status_code == 201
    assert home_assistant.state_calls == 1


def test_preflight_rejects_unavailable_entity(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    response = test_client.post(
        "/api/preflight",
        json=payload() | {"power_meter": {"type": "hass", "entity_id": "sensor.missing"}},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "preflight_failed"


@pytest.mark.parametrize("entity_id", ["sensor.unknown_power", "sensor.text_power"])
def test_preflight_rejects_non_numeric_power_state(tmp_path: Path, entity_id: str) -> None:
    response = client(tmp_path).post(
        "/api/preflight",
        json=payload() | {"power_meter": {"type": "hass", "entity_id": entity_id}},
    )

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
    current = {}
    for _ in range(50):
        current_response = test_client.get("/api/session/current")
        assert current_response.status_code == 200
        current = current_response.json()
        if current["state"] == "completed":
            break
        time.sleep(0.02)
    assert current["progress"]["estimated_remaining_seconds"] == 0
    assert current["operating_point"] == {"type": "light", "on": True, "brightness": 128}
    files = test_client.get("/api/session/current/files")
    assert files.json()[0]["name"] == "LCT010/brightness.csv"
    download = test_client.get("/api/session/current/files/LCT010/brightness.csv")
    assert download.status_code == 200
    diagnostics = test_client.get("/api/session/current/diagnostics")
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


def test_session_summary_is_exposed(tmp_path: Path) -> None:
    app = create_app(data_root=tmp_path, hass_token="test-token", trusted_ingress_only=False)  # noqa: S106
    app.state.context.home_assistant = FakeClient()
    app.state.context.coordinator = MeasurementCoordinator(SessionStorage(tmp_path), SummaryService)
    test_client = TestClient(app)

    run_payload = {
        "measure_type": MeasureType.AVERAGE,
        "power_meter": {"type": "hass", "entity_id": "sensor.test_power"},
        "duration": 30,
    }
    assert test_client.post("/api/sessions", json=run_payload).status_code == 201

    current = {}
    for _ in range(50):
        current = test_client.get("/api/session/current").json()
        if current["state"] == "completed":
            break
        time.sleep(0.02)

    assert current["state"] == "completed"
    assert current["summary"] == {"Average power": "42.3 W", "Duration": "30 s"}


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
    assert set(paths["/api/session/current/diagnostics"]) == {"get"}
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


def test_health_endpoint_for_container_healthcheck(tmp_path: Path) -> None:
    response = client(tmp_path).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_bypasses_ingress_source_check(tmp_path: Path) -> None:
    response = client(tmp_path, trusted_ingress_only=True).get("/health")

    assert response.status_code == 200


def test_settings_default_and_update(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    assert test_client.get("/api/settings").json() == {
        "default_power_entity_id": None,
        "default_measure_device": None,
        "power_meter": "hass",
        "shelly_ip": None,
        "measurement_defaults": {
            "sleep_time": 2.0,
            "sample_count": 1,
            "sleep_time_sample": 1,
            "max_retries": 5,
            "max_nudges": 0,
        },
    }

    updated = test_client.put(
        "/api/settings",
        json={
            "default_power_entity_id": "sensor.test_power",
            "default_measure_device": "Shelly Plug S",
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

    reloaded = test_client.get("/api/settings").json()
    assert reloaded["default_power_entity_id"] == "sensor.test_power"
    assert reloaded["default_measure_device"] == "Shelly Plug S"
    assert reloaded["measurement_defaults"]["sample_count"] == 4
    effective_defaults = test_client.get("/api/capabilities").json()["defaults"]
    assert effective_defaults["sample_count"] == 4
    assert effective_defaults["sleep_time"] == pytest.approx(3.5)


def test_settings_rejects_invalid_entity(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    response = test_client.put("/api/settings", json={"default_power_entity_id": "not-an-entity"})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_settings_rejects_invalid_measurement_defaults(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    response = test_client.put("/api/settings", json={"measurement_defaults": {"max_nudges": 21}})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
