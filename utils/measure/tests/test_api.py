from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from measure.const import MeasureType
from measure.contribution.github import GitHubUser
from measure.dummy_load import DummyLoadCalibration, power_meter_fingerprint
from measure.execution import LightOperatingPoint
from measure.ha_app.api import create_app
from measure.ha_app.contribution import (
    ContributionApiCoordinator,
    ContributionApiError,
    ContributionAuthMethod,
    ContributionAuthStatus,
    ContributionFile,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
    ContributionService,
    ContributionSubmissionResult,
    DeviceFlowPollResponse,
    DeviceFlowStartResponse,
    SharedContributionService,
)
from measure.ha_app.coordinator import MeasurementCoordinator, SessionExecutionContext, SessionMeasurementService
from measure.ha_app.session import SessionControl, SessionEvent, SessionEventType, SessionSnapshot, SessionState
from measure.ha_app.storage import SessionStorage
from measure.home_assistant import HomeAssistantEntityData, HomeAssistantManager
from measure.powermeter.diagnostics import PowerMeterDiagnostics
from measure.powermeter.powermeter import PowerMeter, PowerMeterDiagnosticSample
from measure.powermeter.spec import HassPowerMeterSpec
from measure.request import MeasurementRequest
from measure.runner.runner import RunnerResult
from measure.tuning import MeasurementParameters
from measure.version import measure_version
from pydantic import SecretStr
import pytest


def entity(entity_id: str, state: str, **attributes: Any) -> SimpleNamespace:  # noqa: ANN401
    return SimpleNamespace(
        entity_id=entity_id,
        state=SimpleNamespace(state=state, attributes=attributes),
    )


class FakeClient:
    def __init__(self) -> None:
        self.state_calls = 0
        self.entity_data_calls = 0

    def close(self) -> None:
        return None

    async def discover_zeroconf(self, collection_window: float = 2.0) -> list[dict[str, object]]:
        return []

    def list_entity_registry(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(entity_id="sensor.test_power", device_id="meter-device"),
            SimpleNamespace(entity_id="sensor.test_voltage", device_id="meter-device"),
            SimpleNamespace(entity_id="light.test", device_id="light-device"),
            SimpleNamespace(entity_id="vacuum.test", device_id="vacuum-device"),
            SimpleNamespace(entity_id="sensor.vacuum_battery", device_id="vacuum-device"),
        ]

    def get_device_registry(self) -> list[dict[str, object]]:
        return [
            {"id": "meter-device", "model_id": "PM-001", "model": "Power Meter"},
            {"id": "light-device", "model_id": None, "model": "Hue White Ambiance"},
            {"id": "vacuum-device", "model_id": None, "model": "Test Vacuum"},
        ]

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
                    "vacuum_battery": entity(
                        "sensor.vacuum_battery",
                        "80",
                        friendly_name="Vacuum battery",
                        device_class="battery",
                        unit_of_measurement="%",
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
        self.entity_data_calls += 1
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
        context: SessionExecutionContext,
    ) -> RunnerResult:
        directory = context.artifact_directory
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
        context: SessionExecutionContext,
    ) -> RunnerResult:
        control.progress(completed=30, total=30, mode="Averaging", estimated_remaining="0s")
        summary = {"Average power": "42.3 W", "Duration": "30 s"}
        return RunnerResult(model_json_data={}, summary=summary)


class FakeContributionService(ContributionService):
    def __init__(self) -> None:
        self.preview_calls = 0
        self.submit_calls = 0
        self.username: str | None = None

    def auth_status(self) -> ContributionAuthStatus:
        if self.username is None:
            return ContributionAuthStatus(authenticated=False)
        return ContributionAuthStatus(
            authenticated=True,
            connected=True,
            method=ContributionAuthMethod.PAT,
            username=self.username,
        )

    def connect_pat(self, token: SecretStr) -> ContributionAuthStatus:
        del token
        self.username = "measure-user"
        return ContributionAuthStatus(
            authenticated=True,
            connected=True,
            method=ContributionAuthMethod.PAT,
            username="measure-user",
        )

    def disconnect(self) -> ContributionAuthStatus:
        self.username = None
        return ContributionAuthStatus(authenticated=False)

    def start_device_flow(self, client_id: str) -> DeviceFlowStartResponse:
        return DeviceFlowStartResponse(
            device_code=f"{client_id}-device",
            user_code="ABCD-EFGH",
            verification_uri="https://github.com/login/device",
            expires_in=900,
            interval=5,
            message="Enter ABCD-EFGH",
        )

    def poll_device_flow(self, client_id: str, device_code: str) -> DeviceFlowPollResponse:
        del client_id, device_code
        self.username = "oauth-user"
        return DeviceFlowPollResponse(
            status="authorized",
            auth=ContributionAuthStatus(
                authenticated=True,
                connected=True,
                method=ContributionAuthMethod.OAUTH_DEVICE,
                username="oauth-user",
            ),
        )

    def build_preview(
        self,
        *,
        session_id: str,
        request: MeasurementRequest,
        artifact_root: Path,
        payload: ContributionPreviewRequest | None,
    ) -> ContributionPreviewResponse:
        del artifact_root
        self.preview_calls += 1
        assert payload is not None
        return ContributionPreviewResponse(
            session_id=session_id,
            eligible=True,
            manufacturer_name=payload.manufacturer_name,
            manufacturer_directory=payload.manufacturer_directory or "signify",
            model_id=payload.model_id,
            product_name=payload.product_name,
            contributor=payload.contributor,
            notes=payload.notes,
            files=[
                ContributionFile(
                    name="model.json",
                    path="profile_library/signify/LCT010/model.json",
                    size=20,
                ),
            ],
            commit_message="feat(profile): add signify LCT010",
            pr_title="Add signify LCT010 power profile",
            pr_body="Body",
            branch_name="powercalc-profile-signify-lct010",
            job_id="job-1",
        )

    def submit(
        self,
        *,
        preview: ContributionPreviewResponse,
        artifact_root: Path,
    ) -> ContributionSubmissionResult:
        del preview, artifact_root
        self.submit_calls += 1
        time.sleep(0.05)
        return ContributionSubmissionResult(
            pull_request_url="https://github.com/example/pull/1",
            message="Contribution submitted",
        )


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


def client(tmp_path: Path, *, trusted_ingress_only: bool = False, developer_mode: bool = False) -> TestClient:
    app = create_app(
        data_root=tmp_path,
        hass_token="test-token",  # noqa: S106
        trusted_ingress_only=trusted_ingress_only,
        developer_mode=developer_mode,
    )
    app.state.context.home_assistant = FakeClient()
    app.state.context.power_meter_diagnostics = PowerMeterDiagnostics(
        app.state.context.build_power_meter,
        duration=0,
    )
    app.state.context.coordinator = MeasurementCoordinator(SessionStorage(tmp_path), CompletingService)
    return TestClient(app)


def test_app_metadata_uses_the_runtime_measure_version(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    assert test_client.app.version == measure_version()
    assert test_client.get("/openapi.json").json()["info"]["version"] == measure_version()


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
        "min_sat": defaults.min_sat,
        "max_sat": defaults.max_sat,
        "min_hue": defaults.min_hue,
        "max_hue": defaults.max_hue,
        "sleep_initial": defaults.sleep_initial,
        "sleep_standby": defaults.sleep_standby,
        "effect_bri_steps": defaults.effect_bri_steps,
        "measure_time_effect": defaults.measure_time_effect,
        "measure_time_effect_min": defaults.measure_time_effect_min,
    }
    assert capabilities.json()["limits"]["ct_bri_steps"] == {"min": 1, "max": 10}
    assert capabilities.json()["limits"]["min_sat"] == {"min": 1, "max": 255}
    assert capabilities.json()["developer_mode"] is False
    assert client(tmp_path, developer_mode=True).get("/api/capabilities").json()["developer_mode"] is True
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


def test_entity_catalog_categorizes_one_fresh_snapshot(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    home_assistant = test_client.app.state.context.home_assistant

    response = test_client.get("/api/entity-catalog")

    assert response.status_code == 200
    assert home_assistant.entity_data_calls == 1
    assert [item["entity_id"] for item in response.json()["lights"]] == ["light.test"]
    assert [item["entity_id"] for item in response.json()["powers"]] == ["sensor.test_power"]
    assert [item["entity_id"] for item in response.json()["voltages"]] == ["sensor.test_voltage"]

    assert test_client.get("/api/entity-catalog").status_code == 200
    assert home_assistant.entity_data_calls == 2


def test_dummy_load_calibration_is_returned_only_for_the_configured_meter(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    settings = {
        "default_power_entity_id": "sensor.test_power",
        "default_measure_device": "Test meter",
        "power_meter": "hass",
    }
    assert test_client.put("/api/settings", json=settings).status_code == 200
    calibration = DummyLoadCalibration(
        description="40 W incandescent bulb",
        resistance=1322.5,
        calibrated_at="2026-07-16T12:00:00Z",
        power_meter_fingerprint=power_meter_fingerprint(
            HassPowerMeterSpec(
                entity_id="sensor.test_power",
                voltage_entity_id="sensor.test_voltage",
            ),
        ),
    )
    test_client.app.state.context.storage.save_dummy_load_calibration(calibration)

    response = test_client.get("/api/dummy-load/calibration")

    assert response.status_code == 200
    assert response.json()["resistance"] == pytest.approx(1322.5)

    settings["default_power_entity_id"] = "sensor.other_power"
    assert test_client.put("/api/settings", json=settings).status_code == 200
    assert test_client.get("/api/dummy-load/calibration").json() is None


def test_dummy_load_preflight_requires_voltage_and_includes_calibration_time(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    request = payload() | {
        "dummy_load": {
            "mode": "calibrate",
            "description": "40 W incandescent bulb",
        },
    }

    response = test_client.post("/api/preflight", json=request)

    assert response.status_code == 200
    assert response.json()["estimated_duration_seconds"] >= 600
    assert any("at least 10 minutes" in warning for warning in response.json()["warnings"])

    request["power_meter"] = {
        "type": "hass",
        "entity_id": "sensor.test_power",
        "voltage_entity_id": None,
    }
    response = test_client.post("/api/preflight", json=request)
    assert response.status_code == 422
    assert "voltage sensor is required" in response.json()["message"]


def test_charging_preflight_returns_discovered_battery_sensor(tmp_path: Path) -> None:
    response = client(tmp_path).post(
        "/api/preflight",
        json={
            "measure_type": "charging",
            "power_meter": {"type": "hass", "entity_id": "sensor.test_power"},
            "controller": {"type": "hass", "entity_id": "vacuum.test"},
            "charging_device_type": "vacuum_robot",
        },
    )

    assert response.status_code == 200
    assert response.json()["battery_level_entity_id"] == "sensor.vacuum_battery"
    assert response.json()["battery_level_attribute"] is None


def test_shelly_dummy_load_preflight_builds_and_probes_the_meter_once(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    context = test_client.app.state.context
    meter = MagicMock(spec=PowerMeter)
    meter.has_voltage_support.return_value = True
    meter.diagnostic_sample.return_value = PowerMeterDiagnosticSample(power=4.2, raw_value="4.2", reported_at=100)
    builder = MagicMock(return_value=meter)
    context.power_meter_diagnostics = PowerMeterDiagnostics(builder, duration=0)
    request = payload() | {
        "power_meter": {"type": "shelly", "device_ip": "192.0.2.1"},
        "dummy_load": {"mode": "calibrate", "description": "40 W incandescent bulb"},
    }

    with patch.object(context, "build_power_meter", builder):
        response = test_client.post("/api/preflight", json=request)

    assert response.status_code == 200
    builder.assert_called_once()
    meter.has_voltage_support.assert_called_once_with()
    meter.diagnostic_sample.assert_called_once_with()


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
    assert dummy.json()["supports_voltage"] is True

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
    assert validated.json()["supports_voltage"] is False
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
    assert home_assistant.state_calls == 2
    assert test_client.post("/api/sessions", json=payload()).status_code == 201
    assert home_assistant.state_calls == 2


def test_preflight_rejects_unavailable_entity(tmp_path: Path) -> None:
    test_client = client(tmp_path)

    response = test_client.post(
        "/api/preflight",
        json=payload() | {"power_meter": {"type": "hass", "entity_id": "sensor.missing"}},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "preflight_failed"


def test_preflight_rejects_cli_only_power_meter_adapter(tmp_path: Path) -> None:
    response = client(tmp_path).post(
        "/api/preflight",
        json={
            "measure_type": "average",
            "power_meter": {"type": "kasa", "device_ip": "192.0.2.1"},
            "duration": 60,
        },
    )

    assert response.status_code == 422
    assert response.json()["message"] == "Kasa power meters are not supported by the Home Assistant app"


def test_preflight_rejects_cli_only_controller_adapter(tmp_path: Path) -> None:
    request = payload()
    request["controller"] = {"type": "hue", "bridge_ip": "192.0.2.2", "light": "1"}

    response = client(tmp_path).post("/api/preflight", json=request)

    assert response.status_code == 422
    assert response.json()["message"] == "Hue light controllers are not supported by the Home Assistant app"


def test_preflight_allows_dummy_adapters_only_in_developer_mode(tmp_path: Path) -> None:
    request = {
        "measure_type": "average",
        "power_meter": {"type": "dummy"},
        "duration": 1,
    }

    rejected = client(tmp_path).post("/api/preflight", json=request)
    accepted = client(tmp_path, developer_mode=True).post("/api/preflight", json=request)

    assert rejected.status_code == 422
    assert rejected.json()["message"] == "Dummy power meters require developer mode in the Home Assistant app"
    assert accepted.status_code == 200


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
    plots = test_client.get("/api/session/current/plots")
    assert plots.status_code == 200
    assert plots.json()["partial"] is False
    assert plots.json()["warnings"] == []
    assert plots.json()["plots"][0]["id"] == "brightness"
    assert plots.json()["plots"][0]["series"][0]["points"] == [
        {"x": 1.0, "y": 1.0, "color": None},
    ]
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


def test_diagnostics_retains_only_the_latest_thousand_events(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    assert test_client.post("/api/sessions", json=payload()).status_code == 201
    coordinator = test_client.app.state.context.coordinator
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
    storage = test_client.app.state.context.storage

    with patch.object(storage, "load_events", return_value=events) as load_events:
        response = test_client.get("/api/session/current/diagnostics")

    assert response.status_code == 200
    load_events.assert_called_once_with(coordinator.current.id, limit=1001)
    report = response.json()
    assert len(report["events"]) == 1000
    assert report["events"][0]["sequence"] == 2
    assert report["events_truncated"] is True
    assert report["event_limit"] == 1000


def test_session_summary_is_exposed(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    test_client.app.state.context.coordinator = MeasurementCoordinator(SessionStorage(tmp_path), SummaryService)

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
    assert set(paths["/api/session/current/plots"]) == {"get"}
    assert set(paths["/api/session/current/files/{name}"]) == {"get"}
    assert set(paths["/api/dummy-load/calibration"]) == {"get"}
    assert set(paths["/api/contribution/auth"]) == {"get", "put", "delete"}
    assert set(paths["/api/contribution/auth/device"]) == {"post"}
    assert set(paths["/api/contribution/auth/device/{flow_id}"]) == {"post"}
    assert set(paths["/api/contribution/status"]) == {"get"}
    assert set(paths["/api/session/current/contribution"]) == {"get", "post"}
    assert set(paths["/api/session/current/contribution/preview"]) == {"post"}


def test_contribution_device_flow_reports_configuration_and_uses_injected_service(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    unavailable = test_client.post("/api/contribution/auth/device")
    assert unavailable.status_code == 401
    assert unavailable.json()["code"] == "auth_unavailable"
    assert test_client.get("/api/contribution/auth").json()["device_flow_available"] is False

    service = FakeContributionService()
    context = test_client.app.state.context
    context.contribution = ContributionApiCoordinator(
        context.storage,
        service_factory=lambda: service,
        oauth_client_id="client-1",
    )

    started = test_client.post("/api/contribution/auth/device")
    assert started.status_code == 200
    assert "device_code" not in started.json()
    flow_id = started.json()["flow_id"]

    polled = test_client.post(f"/api/contribution/auth/device/{flow_id}")
    assert polled.status_code == 200
    assert polled.json()["status"] == "authorized"
    assert polled.json()["auth"]["authenticated"] is True
    assert polled.json()["auth"]["username"] == "oauth-user"
    assert polled.json()["auth"]["device_flow_available"] is True

    unknown = test_client.post("/api/contribution/auth/device/unknown-flow")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "flow_not_found"
    completed = test_client.post(f"/api/contribution/auth/device/{flow_id}")
    assert completed.status_code == 404


def test_contribution_pat_rejects_reported_insufficient_scope(tmp_path: Path) -> None:
    github = MagicMock()
    github.fetch_authenticated_user.return_value = GitHubUser(
        login="measure-user",
        scopes=("read:user",),
        scopes_reported=True,
    )
    with (
        patch("measure.ha_app.contribution.service.GitHubClient", return_value=github),
        pytest.raises(ContributionApiError, match="must grant public repository and workflow access"),
    ):
        SharedContributionService(tmp_path).connect_pat(SecretStr("github_pat_test"))


def test_contribution_preview_submit_and_artifact_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWERCALC_GITHUB_REPOSITORY", "test-owner/powercalc-sandbox")
    monkeypatch.setenv("POWERCALC_GITHUB_BRANCH", "main")
    test_client = client(tmp_path)
    service = FakeContributionService()
    context = test_client.app.state.context
    context.contribution = ContributionApiCoordinator(context.storage, service_factory=lambda: service)

    assert test_client.post("/api/sessions", json=payload()).status_code == 201
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001

    auth = test_client.put("/api/contribution/auth", json={"token": "github_pat_test"})
    assert auth.status_code == 200
    assert auth.json()["authenticated"] is True
    assert auth.json()["username"] == "measure-user"
    settings_path = tmp_path / "settings.json"
    if settings_path.exists():
        assert "github_pat_test" not in settings_path.read_text(encoding="utf-8")

    draft = test_client.get("/api/session/current/contribution")
    assert draft.status_code == 200
    assert draft.json()["eligible"] is False
    assert draft.json()["repository"] == "test-owner/powercalc-sandbox"
    assert draft.json()["base_branch"] == "main"

    preview = test_client.post(
        "/api/session/current/contribution/preview",
        json={
            "manufacturer_name": "Signify",
            "manufacturer_directory": "signify",
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
    assert service.preview_calls == 1
    assert service.submit_calls == 0

    unconfirmed = test_client.post(
        "/api/session/current/contribution",
        json={
            "manufacturer_name": "Signify",
            "manufacturer_directory": "signify",
            "model_id": "LCT010",
            "product_name": "Test light",
            "contributor": "measure-user",
            "notes": "No aliases.",
            "confirmed": False,
        },
    )
    assert unconfirmed.status_code == 400
    assert service.submit_calls == 0

    submitted = test_client.post(
        "/api/session/current/contribution",
        json={
            "manufacturer_name": "Signify",
            "manufacturer_directory": "signify",
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

    status = test_client.get("/api/contribution/status")
    assert status.status_code == 200
    assert status.json()["state"] == "submitted"
    assert status.json()["submission_url"] == "https://github.com/example/pull/1"
    assert status.json()["session_id"] == test_client.get("/api/session/current").json()["session_id"]

    files = test_client.get("/api/session/current/files").json()
    assert [item["name"] for item in files] == ["LCT010/brightness.csv"]
    diagnostics = test_client.get("/api/session/current/diagnostics")
    assert "github_pat_test" not in diagnostics.text


def test_contribution_preview_rejects_unsupported_generated_session(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    context = test_client.app.state.context
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
    assert test_client.post("/api/sessions", json=run_payload).status_code == 201
    assert context.coordinator._worker is not None  # noqa: SLF001
    context.coordinator._worker.join(timeout=5)  # noqa: SLF001
    artifact_root = context.storage.artifact_directory(context.coordinator.current.id, "average-device")
    artifact_root.mkdir(parents=True)
    (artifact_root / "model.json").write_text("{}", encoding="utf-8")

    response = test_client.post(
        "/api/session/current/contribution/preview",
        json={
            "manufacturer_name": "Acme",
            "manufacturer_directory": "acme",
            "model_id": "average-device",
            "product_name": "Average device",
            "contributor": "measure-user",
            "notes": "",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "artifacts_required"
    assert service.preview_calls == 0


def test_plot_endpoint_rejects_active_session(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    coordinator = test_client.app.state.context.coordinator
    now = "2026-07-12T12:00:00Z"
    coordinator._snapshot = SessionSnapshot(id="active", state=SessionState.RUNNING, created_at=now, updated_at=now)  # noqa: SLF001

    response = test_client.get("/api/session/current/plots")

    assert response.status_code == 409


def test_plot_endpoint_marks_terminal_incomplete_session_as_partial(tmp_path: Path) -> None:
    test_client = client(tmp_path)
    assert test_client.post("/api/sessions", json=payload()).status_code == 201
    coordinator = test_client.app.state.context.coordinator
    assert coordinator._worker is not None  # noqa: SLF001
    coordinator._worker.join(timeout=5)  # noqa: SLF001
    assert coordinator.current is not None and coordinator.current.state is SessionState.COMPLETED
    coordinator._snapshot = replace(coordinator.current, state=SessionState.CANCELLED)  # noqa: SLF001

    response = test_client.get("/api/session/current/plots")

    assert response.status_code == 200
    assert response.json()["partial"] is True
    assert response.json()["plots"][0]["id"] == "brightness"


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
        "fast_test_mode": False,
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


def test_fast_test_mode_requires_developer_mode_and_dummy_adapters(tmp_path: Path) -> None:
    regular_client = client(tmp_path)
    rejected = regular_client.put("/api/settings", json={"fast_test_mode": True})

    assert rejected.status_code == 400
    assert rejected.json()["message"] == "Fast test mode requires developer mode"

    developer_client = client(tmp_path, developer_mode=True)
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


def test_fast_test_mode_does_not_modify_real_measurement_requests(tmp_path: Path) -> None:
    test_client = client(tmp_path, developer_mode=True)
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
