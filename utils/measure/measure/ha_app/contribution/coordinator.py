from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import os
from threading import Lock
import time
from uuid import uuid4

from pydantic import SecretStr

from measure.ha_app.contribution.models import (
    SUPPORTED_MEASURE_TYPES,
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionAuthStatus,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
    ContributionService,
    ContributionState,
    ContributionStatus,
    ContributionSubmissionResult,
    ContributionSubmitRequest,
    DeviceFlowPollResponse,
    DeviceFlowStartResponse,
)
from measure.ha_app.contribution.service import _draft_from_request, create_contribution_service
from measure.ha_app.session import ACTIVE_SESSION_STATES, SessionSnapshot, SessionState, utc_now
from measure.ha_app.storage import SessionStorage
from measure.request import MeasurementRequest

_LOGGER = logging.getLogger("measure")
_OAUTH_CLIENT_ID_ENV = "POWERCALC_GITHUB_CLIENT_ID"


@dataclass(frozen=True)
class _DeviceFlow:
    device_code: str
    expires_at: float


class ContributionApiCoordinator:
    def __init__(
        self,
        storage: SessionStorage,
        *,
        service_factory: Callable[[], ContributionService] | None = None,
        oauth_client_id: str | None = None,
    ) -> None:
        self._storage = storage
        self._service_factory = service_factory or (lambda: create_contribution_service(storage.data_root))
        self._oauth_client_id = oauth_client_id if oauth_client_id is not None else os.environ.get(_OAUTH_CLIENT_ID_ENV)
        self._lock = Lock()
        self._device_flows: dict[str, _DeviceFlow] = {}
        self._status = storage.load_contribution_status()
        if self._status.state == ContributionState.SUBMITTING:
            self._status = self._status.model_copy(
                update={
                    "state": ContributionState.FAILED,
                    "error": "App stopped during contribution submission; preview can be submitted again",
                    "updated_at": utc_now(),
                },
            )
            storage.save_contribution_status(self._status)

    @property
    def device_flow_available(self) -> bool:
        return bool(self._oauth_client_id)

    def auth_status(self) -> ContributionAuthStatus:
        status = self._service_factory().auth_status()
        return status.model_copy(update={"device_flow_available": self.device_flow_available})

    def connect_pat(self, token: SecretStr) -> ContributionAuthStatus:
        status = self._service_factory().connect_pat(token)
        return status.model_copy(update={"device_flow_available": self.device_flow_available})

    def disconnect(self) -> ContributionAuthStatus:
        status = self._service_factory().disconnect()
        return status.model_copy(update={"device_flow_available": self.device_flow_available})

    def start_device_flow(self) -> DeviceFlowStartResponse:
        client_id = self._require_oauth_client_id()
        response = self._service_factory().start_device_flow(client_id)
        flow_id = uuid4().hex
        with self._lock:
            self._prune_device_flows()
            self._device_flows[flow_id] = _DeviceFlow(
                device_code=response.device_code,
                expires_at=time.monotonic() + response.expires_in,
            )
        return response.model_copy(update={"flow_id": flow_id})

    def poll_device_flow(self, flow_id: str) -> DeviceFlowPollResponse:
        client_id = self._require_oauth_client_id()
        with self._lock:
            self._prune_device_flows()
            flow = self._device_flows.get(flow_id)
        if flow is None:
            raise ContributionApiError(
                ContributionApiErrorCode.FLOW_NOT_FOUND,
                "GitHub Device Flow is unknown or expired; start a new login",
            )
        response = self._service_factory().poll_device_flow(client_id, flow.device_code)
        if response.status in {"authorized", "expired", "denied"}:
            with self._lock:
                self._device_flows.pop(flow_id, None)
        auth = (
            response.auth.model_copy(update={"device_flow_available": self.device_flow_available})
            if response.auth
            else None
        )
        return response.model_copy(update={"auth": auth})

    def status(self) -> ContributionStatus:
        with self._lock:
            return self._status

    def draft(self, snapshot: SessionSnapshot) -> ContributionPreviewResponse:
        self._require_completed_session(snapshot)
        request = self._storage.load_request(snapshot.id)
        return _draft_from_request(
            session_id=snapshot.id,
            request=request,
            artifact_root=self._storage.artifact_directory(snapshot.id, request.model_id),
            auth=self.auth_status(),
        )

    def preview(
        self,
        snapshot: SessionSnapshot,
        payload: ContributionPreviewRequest | None = None,
    ) -> ContributionPreviewResponse:
        self._require_completed_session(snapshot)
        request = self._storage.load_request(snapshot.id)
        self._require_supported_request(request)
        artifact_root = self._storage.artifact_directory(snapshot.id, request.model_id)
        if not artifact_root.exists():
            raise ContributionApiError(
                ContributionApiErrorCode.ARTIFACTS_REQUIRED,
                "No measurement artifacts are available to contribute",
            )
        preview = self._service_factory().build_preview(
            session_id=snapshot.id,
            request=request,
            artifact_root=artifact_root,
            payload=payload,
        )
        with self._lock:
            self._status = ContributionStatus(
                state=ContributionState.PREVIEW_READY,
                session_id=snapshot.id,
                preview=preview,
                message="Preview is ready",
                updated_at=utc_now(),
            )
            self._storage.save_contribution_status(self._status)
        return preview

    def submit(self, snapshot: SessionSnapshot, payload: ContributionSubmitRequest) -> ContributionSubmissionResult:
        if not payload.confirmed:
            raise ContributionApiError(
                ContributionApiErrorCode.PREVIEW_REQUIRED,
                "Review and explicitly confirm the contribution preview before submitting",
            )
        if not self.auth_status().authenticated:
            raise ContributionApiError(
                ContributionApiErrorCode.AUTH_UNAVAILABLE,
                "Connect GitHub before submitting a contribution",
            )
        self._require_completed_session(snapshot)
        request = self._storage.load_request(snapshot.id)
        self._require_supported_request(request)
        with self._lock:
            if self._status.state == ContributionState.SUBMITTING:
                raise ContributionApiError(
                    ContributionApiErrorCode.CONTRIBUTION_ACTIVE,
                    "A contribution is already being submitted",
                )
            if self._status.session_id != snapshot.id or self._status.preview is None:
                raise ContributionApiError(
                    ContributionApiErrorCode.PREVIEW_REQUIRED,
                    "Preview the current session before submitting it",
                )
            preview = self._status.preview
            if _preview_request_values(preview) != _preview_request_values(payload):
                raise ContributionApiError(
                    ContributionApiErrorCode.PREVIEW_REQUIRED,
                    "Contribution details changed after preview; refresh the preview before submitting",
                )
            self._status = self._status.model_copy(
                update={
                    "state": ContributionState.SUBMITTING,
                    "message": "Submitting contribution",
                    "error": None,
                    "updated_at": utc_now(),
                },
            )
            self._storage.save_contribution_status(self._status)
        artifact_root = self._storage.artifact_directory(snapshot.id, request.model_id)
        try:
            result = self._service_factory().submit(
                preview=preview,
                artifact_root=artifact_root,
            )
        except Exception as error:
            _LOGGER.warning("Contribution submission failed: %s", error)
            self._replace_status(
                state=ContributionState.FAILED,
                error=str(error),
                message="Contribution submission failed",
            )
            if isinstance(error, ContributionApiError):
                raise
            raise ContributionApiError(ContributionApiErrorCode.SUBMISSION_FAILED, str(error)) from error
        else:
            self._replace_status(
                state=ContributionState.SUBMITTED,
                submission_url=result.url,
                message=result.message,
                error=None,
            )
            return result.model_copy(
                update={"pull_request_url": result.pull_request_url or result.url},
            )

    def _require_oauth_client_id(self) -> str:
        if not self._oauth_client_id:
            raise ContributionApiError(
                ContributionApiErrorCode.AUTH_UNAVAILABLE,
                "GitHub Device Flow is unavailable because POWERCALC_GITHUB_CLIENT_ID is not configured",
            )
        return self._oauth_client_id

    def _prune_device_flows(self) -> None:
        """Drop expired flows; must be called while holding the lock."""
        now = time.monotonic()
        expired = [flow_id for flow_id, flow in self._device_flows.items() if flow.expires_at <= now]
        for flow_id in expired:
            del self._device_flows[flow_id]

    def _replace_status(self, **updates: object) -> None:
        with self._lock:
            self._status = self._status.model_copy(update=updates | {"updated_at": utc_now()})
            self._storage.save_contribution_status(self._status)

    @staticmethod
    def _require_completed_session(snapshot: SessionSnapshot) -> None:
        if snapshot.state in ACTIVE_SESSION_STATES:
            raise ContributionApiError(
                ContributionApiErrorCode.SESSION_NOT_READY,
                "Contribution is available after the measurement stops",
            )
        if snapshot.state is not SessionState.COMPLETED:
            raise ContributionApiError(
                ContributionApiErrorCode.SESSION_NOT_READY,
                "Contribution requires a completed measurement session",
            )

    @staticmethod
    def _require_supported_request(request: MeasurementRequest) -> None:
        if request.measure_type not in SUPPORTED_MEASURE_TYPES:
            raise ContributionApiError(
                ContributionApiErrorCode.ARTIFACTS_REQUIRED,
                "Automatic contribution is available for light, speaker, fan, and charging profiles",
            )


def _preview_request_values(value: ContributionPreviewResponse | ContributionPreviewRequest) -> tuple[str, ...]:
    return (
        value.manufacturer_name,
        value.manufacturer_directory or "",
        value.model_id,
        value.product_name,
        value.contributor,
        value.notes,
    )
