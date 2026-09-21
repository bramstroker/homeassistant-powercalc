from pathlib import Path
from unittest.mock import MagicMock, patch

from measure.controller.light.spec import DummyLightControllerSpec
from measure.ha_app.contribution.coordinator import ContributionApiCoordinator
from measure.ha_app.contribution.models import (
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionAuthStatus,
    ContributionService,
    DeviceFlowPollResponse,
    DeviceFlowPollStatus,
    DeviceFlowStart,
)
from measure.ha_app.session import SessionSnapshot, SessionState
from measure.ha_app.storage import SessionStorage
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import AverageMeasurementRequest, LightMeasurementRequest, parse_measurement_request
import pytest


@pytest.mark.parametrize(
    "connections,recorder,expected",
    [
        ({"light.one": "zigbee", "light.two": "zigbee"}, False, {"connectivity": ["zigbee"]}),
        ({"light.one": "zigbee", "light.two": "zwave"}, False, None),
        ({"light.one": "zigbee", "light.two": None}, False, None),
        ({"light.one": "zigbee"}, False, None),
        ({}, False, None),
        ({"light.one": "zigbee", "light.two": "zwave"}, True, {"connectivity": ["zigbee"]}),
    ],
)
def test_draft_connectivity_requires_consensus_among_contributed_entities(
    tmp_path: Path, connections: dict[str, str | None], recorder: bool, expected: dict[str, object] | None
) -> None:
    entity_ids = ["light.one", "light.two"]
    request = parse_measurement_request(
        {
            "measure_type": "recorder",
            "recorder_purpose": "complex_profile",
            "profile_recipe": "generic",
            "tracked_entity_ids": entity_ids,
            "power_meter": {"type": "dummy"},
        }
        if recorder
        else {
            "measure_type": "light",
            "measure_device": "Test meter",
            "controller": {"type": "hass_multi", "entity_ids": entity_ids},
            "power_meter": {"type": "dummy"},
        }
    )
    storage = SessionStorage(tmp_path)
    snapshot = SessionSnapshot(
        id="session", state=SessionState.COMPLETED, created_at="2026-09-20", updated_at="2026-09-20"
    )
    storage.create(snapshot, request)
    service = create_service()
    service.auth_status.return_value = ContributionAuthStatus(authenticated=False)
    resolver = MagicMock(return_value=connections)
    coordinator = ContributionApiCoordinator(storage, service_factory=lambda: service, resolve_connectivity=resolver)

    assert coordinator.draft(snapshot).device_specs == expected
    resolver.assert_called_once_with(entity_ids[:1] if recorder else entity_ids)


def create_service() -> MagicMock:
    service = MagicMock(spec=ContributionService)
    service.start_device_flow.return_value = DeviceFlowStart(
        device_code="secret-device-code",
        user_code="ABCD",
        verification_uri="https://github.com/login/device",
        expires_in=60,
        interval=5,
        message="Enter the code",
    )
    return service


def test_expired_device_flow_is_not_polled(tmp_path: Path) -> None:
    service = create_service()
    coordinator = ContributionApiCoordinator(
        SessionStorage(tmp_path), service_factory=lambda: service, oauth_client_id="client-id"
    )
    with patch("measure.ha_app.contribution.coordinator.time.monotonic", return_value=100):
        flow = coordinator.start_device_flow()
    with (
        patch("measure.ha_app.contribution.coordinator.time.monotonic", return_value=160),
        pytest.raises(ContributionApiError) as error,
    ):
        coordinator.poll_device_flow(flow.flow_id)

    assert error.value.code == ContributionApiErrorCode.FLOW_NOT_FOUND
    service.poll_device_flow.assert_not_called()
    assert "device_code" not in flow.model_dump()


@pytest.mark.parametrize("status", [DeviceFlowPollStatus.PENDING, DeviceFlowPollStatus.SLOW_DOWN])
def test_pending_device_flow_can_be_polled_again(tmp_path: Path, status: DeviceFlowPollStatus) -> None:
    service = create_service()
    response = DeviceFlowPollResponse(status=status, retry_after=10)
    service.poll_device_flow.return_value = response
    coordinator = ContributionApiCoordinator(
        SessionStorage(tmp_path), service_factory=lambda: service, oauth_client_id="client-id"
    )

    flow = coordinator.start_device_flow()
    assert coordinator.poll_device_flow(flow.flow_id) == response
    assert coordinator.poll_device_flow(flow.flow_id) == response

    assert service.poll_device_flow.call_count == 2
    service.poll_device_flow.assert_called_with("client-id", "secret-device-code")


def test_disconnect_preserves_device_flow_availability(tmp_path: Path) -> None:
    service = create_service()
    service.disconnect.return_value = ContributionAuthStatus(authenticated=False)
    coordinator = ContributionApiCoordinator(
        SessionStorage(tmp_path), service_factory=lambda: service, oauth_client_id="client-id"
    )

    status = coordinator.disconnect()

    assert not status.authenticated
    assert status.device_flow_available
    service.disconnect.assert_called_once_with()


@pytest.mark.parametrize(
    "state", [SessionState.RUNNING, SessionState.READY, SessionState.FAILED, SessionState.CANCELLED]
)
def test_preview_requires_completed_session(tmp_path: Path, state: SessionState) -> None:
    service = create_service()
    coordinator = ContributionApiCoordinator(SessionStorage(tmp_path), service_factory=lambda: service)
    snapshot = SessionSnapshot(id="session", state=state, created_at="2026-09-18", updated_at="2026-09-18")

    with pytest.raises(ContributionApiError) as error:
        coordinator.preview(snapshot)

    assert error.value.code == ContributionApiErrorCode.SESSION_NOT_READY
    service.build_preview.assert_not_called()


def test_preview_requires_measurement_artifacts(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    snapshot = SessionSnapshot(
        id="session", state=SessionState.COMPLETED, created_at="2026-09-18", updated_at="2026-09-18"
    )
    storage.create(
        snapshot,
        LightMeasurementRequest(
            model_id="lamp",
            measure_device="Test meter",
            power_meter=DummyPowerMeterSpec(),
            controller=DummyLightControllerSpec(),
        ),
    )
    service = create_service()
    coordinator = ContributionApiCoordinator(storage, service_factory=lambda: service)

    with pytest.raises(ContributionApiError) as error:
        coordinator.preview(snapshot)

    assert error.value.code == ContributionApiErrorCode.ARTIFACTS_REQUIRED
    service.build_preview.assert_not_called()


def test_average_measurement_cannot_be_contributed(tmp_path: Path) -> None:
    storage = SessionStorage(tmp_path)
    snapshot = SessionSnapshot(
        id="session", state=SessionState.COMPLETED, created_at="2026-09-18", updated_at="2026-09-18"
    )
    storage.create(snapshot, AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()))
    service = create_service()
    coordinator = ContributionApiCoordinator(storage, service_factory=lambda: service)

    with pytest.raises(ContributionApiError) as error:
        coordinator.preview(snapshot)

    assert error.value.code == ContributionApiErrorCode.ARTIFACTS_REQUIRED
    service.build_preview.assert_not_called()
