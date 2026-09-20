from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from measure.const import MeasureType
from measure.controller.light.const import LutMode
from measure.ha_app.api import create_app
from measure.ha_app.contribution.models import (
    ContributionAuthMethod,
    ContributionAuthStatus,
    ContributionFile,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
    ContributionService,
    ContributionSubmissionResult,
    DeviceFlowPollResponse,
    DeviceFlowPollStatus,
    DeviceFlowStart,
)
from measure.ha_app.coordinator import (
    MeasurementCoordinator,
    SessionExecutionContext,
    SessionMeasurementService,
)
from measure.ha_app.light_probe import LightLoadProbePoint, LightLoadProbeResult
from measure.ha_app.session import SessionControl
from measure.ha_app.storage import SessionStorage
from measure.home_assistant.client import HomeAssistantEntityData
from measure.powermeter.diagnostics import PowerMeterDiagnostics
from measure.request import MeasurementRequest
from measure.runner.interaction import LightOperatingPoint
from measure.runner.runner import RunnerResult
from pydantic import SecretStr


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

    def get_config(self) -> dict[str, str]:
        return {"state": "RUNNING"}

    async def discover_zeroconf(self, collection_window: float = 2.0) -> list[dict[str, object]]:
        return []

    def list_entity_registry(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(entity_id="sensor.test_power", device_id="meter-device", platform="shelly"),
            SimpleNamespace(entity_id="sensor.test_voltage", device_id="meter-device", platform="shelly"),
            SimpleNamespace(entity_id="light.test", device_id="light-device", platform="hue"),
            SimpleNamespace(entity_id="vacuum.test", device_id="vacuum-device", platform="roborock"),
            SimpleNamespace(entity_id="sensor.vacuum_battery", device_id="vacuum-device", platform="roborock"),
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

    def start_device_flow(self, client_id: str) -> DeviceFlowStart:
        return DeviceFlowStart(
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
            status=DeviceFlowPollStatus.AUTHORIZED,
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
        integration: str | None = None,
    ) -> ContributionPreviewResponse:
        del artifact_root
        self.preview_calls += 1
        assert payload is not None
        return ContributionPreviewResponse(
            session_id=session_id,
            eligible=True,
            home_assistant={"integration": integration},
            manufacturer_directory="signify",
            **payload.model_dump(exclude_none=True),
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

    def prepared_archive(self, job_id: str) -> bytes:
        assert job_id == "job-1"
        return b"PK\x03\x04prepared-profile"


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


@dataclass
class AppClientFactory:
    data_root: Path
    clients: list[TestClient] = field(default_factory=list)

    def __call__(
        self,
        *,
        trusted_ingress_only: bool = False,
        developer_mode: bool = False,
    ) -> TestClient:
        app = create_app(
            data_root=self.data_root,
            hass_token="test-token",  # noqa: S106
            trusted_ingress_only=trusted_ingress_only,
            developer_mode=developer_mode,
        )
        app.state.context.home_assistant = FakeClient()
        app.state.context.power_meter_diagnostics = PowerMeterDiagnostics(
            app.state.context.create_power_meter,
            duration=0,
        )
        app.state.context.light_load_probe = MagicMock()
        app.state.context.light_load_probe.evaluate.return_value = LightLoadProbeResult(
            checked_variations=1,
            minimum_aggregate_power_w=1.25,
            points=(LightLoadProbePoint(label="Brightness 1", mode=LutMode.BRIGHTNESS, power_w=1.25),),
        )
        app.state.context.coordinator = MeasurementCoordinator(SessionStorage(self.data_root), CompletingService)
        client = TestClient(app, client=("127.0.0.1", 50000))
        self.clients.append(client)
        return client

    def close(self) -> None:
        for client in reversed(self.clients):
            client.close()
