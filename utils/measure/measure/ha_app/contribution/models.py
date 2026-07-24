from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, SecretStr

from measure.const import MeasureType
from measure.contribution.github import UPSTREAM_BRANCH, UPSTREAM_OWNER, UPSTREAM_REPO
from measure.request import MeasurementRequest

SUPPORTED_MEASURE_TYPES = {
    MeasureType.LIGHT,
    MeasureType.SPEAKER,
    MeasureType.FAN,
    MeasureType.CHARGING,
}


class ContributionAuthMethod(StrEnum):
    NONE = "none"
    PAT = "token"
    OAUTH_DEVICE = "device"


class ContributionState(StrEnum):
    """UI-facing contribution state, one per app install, persisted by ``SessionStorage``.

    Tracks where the user is in the preview/submit flow. The per-job source of truth
    is ``measure.contribution.models.ContributionJobStatus``; this state adds the
    app-only ``IDLE``/``PREVIEW_READY`` phases and drives the frontend.
    """

    IDLE = "idle"
    PREVIEW_READY = "preview_ready"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    FAILED = "failed"


class ContributionApiErrorCode(StrEnum):
    AUTH_UNAVAILABLE = "auth_unavailable"
    SESSION_REQUIRED = "session_required"
    SESSION_NOT_READY = "session_not_ready"
    PREVIEW_REQUIRED = "preview_required"
    CONTRIBUTION_ACTIVE = "contribution_active"
    ARTIFACTS_REQUIRED = "artifacts_required"
    INVALID_METADATA = "invalid_metadata"
    FLOW_NOT_FOUND = "flow_not_found"
    SUBMISSION_FAILED = "submission_failed"


class ContributionApiError(Exception):
    def __init__(self, code: ContributionApiErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class ContributionIdentity(BaseModel):
    login: str


class ContributionAuthStatus(BaseModel):
    authenticated: bool
    connected: bool = False
    method: ContributionAuthMethod = ContributionAuthMethod.NONE
    identity: ContributionIdentity | None = None
    username: str | None = None
    device_flow_available: bool = False
    scopes: list[str] = Field(default_factory=list)
    permissions_verified: bool = False


class ConnectPatRequest(BaseModel):
    token: SecretStr = Field(min_length=1)


class DeviceFlowStart(BaseModel):
    """What GitHub returns when a device flow starts, before the app assigns a public flow id.

    ``device_code`` is the secret used to poll for the token; it is excluded from
    serialization so it can never reach a client.
    """

    device_code: str = Field(exclude=True)
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_in: int
    interval: int
    message: str

    def with_flow_id(self, flow_id: str) -> DeviceFlowStartResponse:
        """Attach the app-assigned flow id clients poll with."""
        # vars() rather than model_dump(): the latter drops the excluded device_code.
        return DeviceFlowStartResponse(flow_id=flow_id, **vars(self))


class DeviceFlowStartResponse(DeviceFlowStart):
    flow_id: str


class DeviceFlowPollResponse(BaseModel):
    status: str
    auth: ContributionAuthStatus | None = None
    message: str | None = None


class ContributionFile(BaseModel):
    name: str
    path: str
    size: int
    content: str | None = None
    rendered_json: Any | None = None


class ContributionPreviewRequest(BaseModel):
    manufacturer_name: str = Field(min_length=1, max_length=200)
    manufacturer_directory: str | None = Field(default=None, max_length=120)
    model_id: str = Field(min_length=1, max_length=120)
    product_name: str = Field(min_length=1, max_length=200)
    contributor: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=2_000)


class ContributionSubmitRequest(ContributionPreviewRequest):
    confirmed: Literal[True]


class ContributionPreviewResponse(BaseModel):
    session_id: str
    eligible: bool
    reason: str | None = None
    repository: str = f"{UPSTREAM_OWNER}/{UPSTREAM_REPO}"
    fork_repository: str | None = None
    base_branch: str = UPSTREAM_BRANCH
    base_sha: str | None = None
    manufacturer_name: str
    manufacturer_directory: str
    model_id: str
    product_name: str
    contributor: str
    device_info: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    home_assistant: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    notes: str = ""
    files: list[ContributionFile]
    model_json: Any | None = None
    commit_message: str
    pr_title: str
    pr_body: str
    branch_name: str
    job_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ContributionSubmissionResult(BaseModel):
    status: Literal["success", "failed", "pending"] = "success"
    pull_request_url: str | None = None
    repository: str = f"{UPSTREAM_OWNER}/{UPSTREAM_REPO}"
    branch_name: str | None = None
    message: str


class ContributionStatus(BaseModel):
    state: ContributionState = ContributionState.IDLE
    session_id: str | None = None
    preview: ContributionPreviewResponse | None = None
    submission_url: str | None = None
    message: str | None = None
    error: str | None = None
    updated_at: str | None = None


class ContributionService(Protocol):
    def auth_status(self) -> ContributionAuthStatus: ...

    def connect_pat(self, token: SecretStr) -> ContributionAuthStatus: ...

    def disconnect(self) -> ContributionAuthStatus: ...

    def start_device_flow(self, client_id: str) -> DeviceFlowStart: ...

    def poll_device_flow(self, client_id: str, device_code: str) -> DeviceFlowPollResponse: ...

    def build_preview(
        self,
        *,
        session_id: str,
        request: MeasurementRequest,
        artifact_root: Path,
        payload: ContributionPreviewRequest | None,
    ) -> ContributionPreviewResponse: ...

    def submit(
        self,
        *,
        preview: ContributionPreviewResponse,
        artifact_root: Path,
    ) -> ContributionSubmissionResult: ...


class ContributionServiceFactory(Protocol):
    def __call__(self) -> ContributionService: ...
