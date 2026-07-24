from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
import json
import logging
import os
from pathlib import Path
import shutil
from threading import Lock
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, SecretStr

from measure.const import MeasureType
from measure.contribution.coordinator import (
    ContributionCoordinator as ProfileContributionCoordinator,
    ContributionJobStore,
    conventional_commit_message,
    deterministic_branch,
    human_pull_request_title,
    pull_request_body,
)
from measure.contribution.credentials import CredentialStore, StoredCredential
from measure.contribution.github import (
    REQUIRED_OAUTH_SCOPES,
    UPSTREAM_BRANCH,
    UPSTREAM_OWNER,
    UPSTREAM_REPO,
    GitHubApiError,
    GitHubClient,
    GitHubRepository,
)
from measure.contribution.models import (
    ContributionAuthor,
    ContributionJob,
    ContributionMetadata,
    ContributionPreview as ProfileContributionPreview,
)
from measure.contribution.prepare import ProfilePreparationError, ProfilePreparer
from measure.ha_app.session import ACTIVE_SESSION_STATES, SessionSnapshot, SessionState, utc_now
from measure.ha_app.storage import SessionStorage
from measure.request import MeasurementRequest

_LOGGER = logging.getLogger("measure")
_OAUTH_CLIENT_ID_ENV = "POWERCALC_GITHUB_CLIENT_ID"
_SUPPORTED_MEASURE_TYPES = {
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
    IDLE = "idle"
    PREVIEW_READY = "preview_ready"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    FAILED = "failed"


class ContributionErrorCode(StrEnum):
    AUTH_UNAVAILABLE = "auth_unavailable"
    SESSION_REQUIRED = "session_required"
    SESSION_NOT_READY = "session_not_ready"
    PREVIEW_REQUIRED = "preview_required"
    CONTRIBUTION_ACTIVE = "contribution_active"
    ARTIFACTS_REQUIRED = "artifacts_required"
    SUBMISSION_FAILED = "submission_failed"


class ContributionError(Exception):
    def __init__(self, code: ContributionErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class ContributionIdentity(BaseModel):
    login: str
    name: str | None = None
    avatar_url: str | None = None
    html_url: str | None = None


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


class DeviceFlowStartResponse(BaseModel):
    flow_id: str | None = None
    device_code: str = Field(exclude=True)
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_in: int
    interval: int
    message: str


class DeviceFlowPollResponse(BaseModel):
    status: str
    auth: ContributionAuthStatus | None = None
    message: str | None = None


class ContributionFile(BaseModel):
    name: str
    path: str
    size: int
    media_type: str | None = None
    content: str | None = None
    rendered_json: Any | None = None


class ContributionPreviewRequest(BaseModel):
    manufacturer_name: str = Field(min_length=1)
    manufacturer_directory: str | None = None
    model_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    contributor: str = Field(min_length=1)
    notes: str = ""


class ContributionSubmitRequest(ContributionPreviewRequest):
    confirmed: Literal[True]


class ContributionPreview(BaseModel):
    session_id: str
    title: str
    body: str
    eligible: bool
    reason: str | None = None
    repository: str = f"{UPSTREAM_OWNER}/{UPSTREAM_REPO}"
    fork_repository: str | None = None
    base_branch: str = UPSTREAM_BRANCH
    base_sha: str | None = None
    default_branch: str | None = UPSTREAM_BRANCH
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
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ContributionSubmissionResult(BaseModel):
    status: Literal["success", "failed", "pending"] = "success"
    url: str | None = None
    pull_request_url: str | None = None
    repository: str = f"{UPSTREAM_OWNER}/{UPSTREAM_REPO}"
    branch_name: str | None = None
    message: str


class ContributionStatus(BaseModel):
    state: ContributionState = ContributionState.IDLE
    session_id: str | None = None
    preview: ContributionPreview | None = None
    submission_url: str | None = None
    message: str | None = None
    error: str | None = None
    updated_at: str | None = None


class ContributionService(Protocol):
    def auth_status(self) -> ContributionAuthStatus: ...

    def connect_pat(self, token: SecretStr) -> ContributionAuthStatus: ...

    def disconnect(self) -> ContributionAuthStatus: ...

    def start_device_flow(self, client_id: str) -> DeviceFlowStartResponse: ...

    def poll_device_flow(self, client_id: str, device_code: str) -> DeviceFlowPollResponse: ...

    def build_preview(
        self,
        *,
        session_id: str,
        request: MeasurementRequest,
        artifact_root: Path,
        payload: ContributionPreviewRequest | None,
    ) -> ContributionPreview: ...

    def submit(
        self,
        *,
        preview: ContributionPreview,
        artifact_root: Path,
    ) -> ContributionSubmissionResult: ...


class ContributionServiceFactory(Protocol):
    def __call__(self) -> ContributionService: ...


class SharedContributionService:
    def __init__(self, data_root: Path) -> None:
        self._contribution_root = data_root / "contribution"
        self._credential_store = CredentialStore(self._contribution_root / "credentials.json")
        self._job_store = ContributionJobStore(self._contribution_root / "jobs")

    def auth_status(self) -> ContributionAuthStatus:
        credential = self._credential_store.load()
        if credential is None:
            return ContributionAuthStatus(authenticated=False, connected=False)
        return ContributionAuthStatus(
            authenticated=True,
            connected=True,
            method=ContributionAuthMethod.OAUTH_DEVICE if credential.kind == "oauth" else ContributionAuthMethod.PAT,
            identity=ContributionIdentity(login=credential.github_username or ""),
            username=credential.github_username,
            scopes=list(credential.scopes),
            permissions_verified=credential.permissions_verified,
        )

    def connect_pat(self, token: SecretStr) -> ContributionAuthStatus:
        raw_token = token.get_secret_value()
        try:
            user = GitHubClient(raw_token).validate_user()
        except GitHubApiError as error:
            raise ContributionError(ContributionErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        repository_access_granted = bool({"repo", "public_repo"}.intersection(user.scopes))
        permission_granted = repository_access_granted and "workflow" in user.scopes
        if user.scopes_reported and not permission_granted:
            raise ContributionError(
                ContributionErrorCode.AUTH_UNAVAILABLE,
                "The GitHub token must grant public repository and workflow access",
            )
        self._credential_store.save(
            StoredCredential(
                kind="pat",
                token=raw_token,
                github_username=user.login,
                scopes=user.scopes,
                permissions_verified=permission_granted,
            ),
        )
        return self.auth_status()

    def disconnect(self) -> ContributionAuthStatus:
        self._credential_store.clear()
        return self.auth_status()

    def start_device_flow(self, client_id: str) -> DeviceFlowStartResponse:
        try:
            data = GitHubClient().start_device_flow(client_id, REQUIRED_OAUTH_SCOPES)
        except GitHubApiError as error:
            raise ContributionError(ContributionErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        device_code = str(data["device_code"])
        return DeviceFlowStartResponse(
            flow_id=device_code,
            device_code=device_code,
            user_code=str(data["user_code"]),
            verification_uri=str(data["verification_uri"]),
            verification_uri_complete=str(data["verification_uri_complete"])
            if data.get("verification_uri_complete") is not None
            else None,
            expires_in=int(data["expires_in"]),
            interval=int(data["interval"]),
            message=f"Enter code {data['user_code']} at {data['verification_uri']}",
        )

    def poll_device_flow(self, client_id: str, device_code: str) -> DeviceFlowPollResponse:
        try:
            data = GitHubClient().poll_device_flow(client_id, device_code)
        except GitHubApiError as error:
            raise ContributionError(ContributionErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        oauth_error = data.get("error")
        if oauth_error in {"authorization_pending", "slow_down"}:
            return DeviceFlowPollResponse(
                status="pending",
                message=str(data.get("error_description") or "Authorization pending"),
            )
        if oauth_error in {"expired_token", "access_denied"}:
            return DeviceFlowPollResponse(
                status="expired" if oauth_error == "expired_token" else "denied",
                message=str(data.get("error_description") or oauth_error),
            )
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise ContributionError(
                ContributionErrorCode.AUTH_UNAVAILABLE,
                "GitHub Device Flow did not return an access token",
            )
        try:
            user = GitHubClient(token).validate_user()
        except GitHubApiError as auth_error:
            raise ContributionError(ContributionErrorCode.AUTH_UNAVAILABLE, str(auth_error)) from auth_error
        response_scopes = tuple(scope for scope in str(data.get("scope", "")).split() if scope)
        self._credential_store.save(
            StoredCredential(
                kind="oauth",
                token=token,
                github_username=user.login,
                scopes=user.scopes or response_scopes or REQUIRED_OAUTH_SCOPES,
                permissions_verified=True,
            ),
        )
        return DeviceFlowPollResponse(status="authorized", auth=self.auth_status())

    def build_preview(
        self,
        *,
        session_id: str,
        request: MeasurementRequest,
        artifact_root: Path,
        payload: ContributionPreviewRequest | None,
    ) -> ContributionPreview:
        credential = self._credential_store.load()
        if credential is None:
            raise ContributionError(
                ContributionErrorCode.AUTH_UNAVAILABLE,
                "Connect GitHub before building a contribution preview",
            )
        client = GitHubClient(credential.token)
        try:
            preparer, base_sha = self._reference_preparer(client)
        except GitHubApiError as error:
            raise ContributionError(ContributionErrorCode.SUBMISSION_FAILED, str(error)) from error
        coordinator = ProfileContributionCoordinator(
            preparer=preparer,
            credential_store=self._credential_store,
            job_store=self._job_store,
            github_client=client,
        )
        metadata = _metadata_from_request(request, payload, self.auth_status())
        try:
            job = coordinator.create_job(artifact_root, metadata, base_sha=base_sha)
        except ProfilePreparationError as error:
            raise ContributionError(ContributionErrorCode.ARTIFACTS_REQUIRED, str(error)) from error
        contents = preparer.prepared_contents(artifact_root, metadata, job.preview)
        return _preview_from_job(
            session_id=session_id,
            request=request,
            job=job,
            notes=payload.notes if payload is not None else "",
            contents=contents,
            base_sha=base_sha,
            fork_owner=credential.github_username,
            repository=client.repository,
        )

    def submit(
        self,
        *,
        preview: ContributionPreview,
        artifact_root: Path,
    ) -> ContributionSubmissionResult:
        job_id = preview.metadata.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ContributionError(
                ContributionErrorCode.PREVIEW_REQUIRED,
                "Preview the current session before submitting it",
            )
        credential = self._credential_store.load()
        if credential is None:
            raise ContributionError(
                ContributionErrorCode.AUTH_UNAVAILABLE,
                "Connect GitHub before submitting a contribution",
            )
        client = GitHubClient(credential.token)
        try:
            preparer, base_sha = self._reference_preparer(client)
        except GitHubApiError as error:
            raise ContributionError(ContributionErrorCode.SUBMISSION_FAILED, str(error)) from error
        try:
            job_before_submit = self._job_store.load(job_id)
            latest_preview = preparer.prepare(artifact_root, job_before_submit.metadata)
        except (KeyError, ProfilePreparationError) as error:
            raise ContributionError(ContributionErrorCode.SUBMISSION_FAILED, str(error)) from error
        _validate_latest_preview(job_before_submit, latest_preview, base_sha)
        coordinator = ProfileContributionCoordinator(
            preparer=preparer,
            credential_store=self._credential_store,
            job_store=self._job_store,
            github_client=client,
        )
        job = coordinator.submit(job_id, artifact_root)
        if job.error is not None:
            raise ContributionError(ContributionErrorCode.SUBMISSION_FAILED, job.error.message)
        if job.submission is None:
            raise ContributionError(
                ContributionErrorCode.SUBMISSION_FAILED,
                "Contribution submission did not return a pull request",
            )
        return ContributionSubmissionResult(
            url=job.submission.pull_request_url,
            pull_request_url=job.submission.pull_request_url,
            repository=client.repository.full_name,
            branch_name=job.submission.branch,
            message="Contribution submitted",
        )

    def _reference_preparer(self, client: GitHubClient) -> tuple[ProfilePreparer, str]:
        repository = client.repository
        base_ref = client.get_ref(repository.owner, repository.name, repository.branch)
        if base_ref is None:
            raise ContributionError(
                ContributionErrorCode.SUBMISSION_FAILED,
                f"{repository.full_name} branch {repository.branch} was not found",
            )
        base_sha = str(base_ref["object"]["sha"])
        library_root = self._contribution_root / "reference" / base_sha / "profile_library"
        schema_path = library_root / "model_schema.json"
        index_path = library_root / "library.json"
        for path, upstream_path in (
            (schema_path, "profile_library/model_schema.json"),
            (index_path, "profile_library/library.json"),
        ):
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f"{path.suffix}.tmp")
            temporary.write_bytes(client.get_file(repository.owner, repository.name, upstream_path, base_sha))
            temporary.replace(path)
        reference_root = self._contribution_root / "reference"
        for path in reference_root.iterdir():
            if path.is_dir() and path.name != base_sha:
                shutil.rmtree(path)
        return ProfilePreparer(library_root=library_root, model_schema_path=schema_path), base_sha


class ContributionCoordinator:
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
        self._device_flows: dict[str, str] = {}
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
        if not self._oauth_client_id:
            raise ContributionError(
                ContributionErrorCode.AUTH_UNAVAILABLE,
                "GitHub Device Flow is unavailable because POWERCALC_GITHUB_CLIENT_ID is not configured",
            )
        response = self._service_factory().start_device_flow(self._oauth_client_id)
        flow_id = uuid4().hex
        with self._lock:
            self._device_flows[flow_id] = response.device_code
        return response.model_copy(update={"flow_id": flow_id})

    def poll_device_flow(self, flow_id: str) -> DeviceFlowPollResponse:
        if not self._oauth_client_id:
            raise ContributionError(
                ContributionErrorCode.AUTH_UNAVAILABLE,
                "GitHub Device Flow is unavailable because POWERCALC_GITHUB_CLIENT_ID is not configured",
            )
        with self._lock:
            device_code = self._device_flows.get(flow_id)
        if device_code is None:
            raise ContributionError(
                ContributionErrorCode.AUTH_UNAVAILABLE,
                "GitHub Device Flow is unknown or expired; start a new login",
            )
        response = self._service_factory().poll_device_flow(self._oauth_client_id, device_code)
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

    def draft(self, snapshot: SessionSnapshot) -> ContributionPreview:
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
    ) -> ContributionPreview:
        self._require_completed_session(snapshot)
        request = self._storage.load_request(snapshot.id)
        self._require_supported_request(request)
        artifact_root = self._storage.artifact_directory(snapshot.id, request.model_id)
        if not artifact_root.exists():
            raise ContributionError(
                ContributionErrorCode.ARTIFACTS_REQUIRED,
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
            raise ContributionError(
                ContributionErrorCode.PREVIEW_REQUIRED,
                "Review and explicitly confirm the contribution preview before submitting",
            )
        if not self.auth_status().authenticated:
            raise ContributionError(
                ContributionErrorCode.AUTH_UNAVAILABLE,
                "Connect GitHub before submitting a contribution",
            )
        self._require_completed_session(snapshot)
        request = self._storage.load_request(snapshot.id)
        self._require_supported_request(request)
        with self._lock:
            if self._status.state == ContributionState.SUBMITTING:
                raise ContributionError(
                    ContributionErrorCode.CONTRIBUTION_ACTIVE,
                    "A contribution is already being submitted",
                )
            if self._status.session_id != snapshot.id or self._status.preview is None:
                raise ContributionError(
                    ContributionErrorCode.PREVIEW_REQUIRED,
                    "Preview the current session before submitting it",
                )
            preview = self._status.preview
            if _preview_request_values(preview) != _preview_request_values(payload):
                raise ContributionError(
                    ContributionErrorCode.PREVIEW_REQUIRED,
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
            if isinstance(error, ContributionError):
                raise
            raise ContributionError(ContributionErrorCode.SUBMISSION_FAILED, str(error)) from error
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

    def _replace_status(self, **updates: object) -> None:
        with self._lock:
            self._status = self._status.model_copy(update=updates | {"updated_at": utc_now()})
            self._storage.save_contribution_status(self._status)

    @staticmethod
    def _require_completed_session(snapshot: SessionSnapshot) -> None:
        if snapshot.state in ACTIVE_SESSION_STATES:
            raise ContributionError(
                ContributionErrorCode.SESSION_NOT_READY,
                "Contribution is available after the measurement stops",
            )
        if snapshot.state is not SessionState.COMPLETED:
            raise ContributionError(
                ContributionErrorCode.SESSION_NOT_READY,
                "Contribution requires a completed measurement session",
            )

    @staticmethod
    def _require_supported_request(request: MeasurementRequest) -> None:
        if request.measure_type not in _SUPPORTED_MEASURE_TYPES:
            raise ContributionError(
                ContributionErrorCode.ARTIFACTS_REQUIRED,
                "Automatic contribution is available for light, speaker, fan, and charging profiles",
            )


def create_contribution_service(data_root: Path) -> ContributionService:
    return SharedContributionService(data_root)


def _metadata_from_request(
    request: MeasurementRequest,
    payload: ContributionPreviewRequest | None,
    auth: ContributionAuthStatus,
) -> ContributionMetadata:
    contributor = payload.contributor if payload is not None else auth.username or "Powercalc user"
    manufacturer = payload.manufacturer_name if payload is not None else "Unknown"
    model_id = payload.model_id if payload is not None else request.model_id
    github_username = auth.username
    if not github_username:
        raise ContributionError(ContributionErrorCode.AUTH_UNAVAILABLE, "Connected GitHub account has no username")
    return ContributionMetadata(
        manufacturer=manufacturer,
        manufacturer_directory=payload.manufacturer_directory if payload is not None else None,
        model_id=model_id,
        product_name=payload.product_name if payload is not None else request.product_name,
        notes=payload.notes if payload is not None else "",
        author=ContributionAuthor(name=contributor, github=github_username),
    )


def _draft_from_request(
    *,
    session_id: str,
    request: MeasurementRequest,
    artifact_root: Path,
    auth: ContributionAuthStatus,
) -> ContributionPreview:
    manufacturer = "Unknown"
    contributor = auth.username or ""
    files = _draft_files(artifact_root)
    supported = request.measure_type in _SUPPORTED_MEASURE_TYPES
    has_model = artifact_root.is_dir() and any(file.path.endswith("model.json") for file in files)
    eligible = supported and has_model
    if not supported:
        reason = "Automatic contribution is available for light, speaker, fan, and charging profiles"
    elif not has_model:
        reason = "Contribution requires a generated model.json artifact"
    else:
        reason = None
    return _preview_response(
        session_id=session_id,
        request=request,
        manufacturer_name=manufacturer,
        manufacturer_directory="unknown",
        model_id=request.model_id,
        product_name=request.product_name,
        contributor=contributor,
        notes="",
        files=files,
        warnings=[],
        eligible=eligible,
        reason=reason,
        job_id=None,
    )


def _preview_from_job(
    *,
    session_id: str,
    request: MeasurementRequest,
    job: ContributionJob,
    notes: str,
    contents: tuple[tuple[str, bytes], ...],
    base_sha: str,
    fork_owner: str | None,
    repository: GitHubRepository,
) -> ContributionPreview:
    content_by_path = dict(contents)
    return _preview_response(
        session_id=session_id,
        request=request,
        manufacturer_name=job.metadata.manufacturer,
        manufacturer_directory=job.preview.manufacturer_directory,
        model_id=job.metadata.model_id,
        product_name=job.metadata.product_name or request.product_name,
        contributor=job.metadata.author.name,
        notes=notes,
        files=[_preview_file(file.path, content_by_path[file.path]) for file in job.preview.files],
        warnings=list(job.preview.warnings),
        eligible=True,
        reason=None,
        job_id=job.id,
        base_sha=base_sha,
        fork_owner=fork_owner,
        commit_message=conventional_commit_message(job.preview),
        pr_title=human_pull_request_title(job.preview),
        pr_body=pull_request_body(job),
        repository=repository,
    )


def _preview_response(
    *,
    session_id: str,
    request: MeasurementRequest,
    manufacturer_name: str,
    manufacturer_directory: str,
    model_id: str,
    product_name: str,
    contributor: str,
    notes: str,
    files: list[ContributionFile],
    warnings: list[str],
    eligible: bool,
    reason: str | None,
    job_id: str | None,
    base_sha: str | None = None,
    fork_owner: str | None = None,
    commit_message: str | None = None,
    pr_title: str | None = None,
    pr_body: str | None = None,
    repository: GitHubRepository | None = None,
) -> ContributionPreview:
    repository = repository or GitHubRepository.from_environment()
    profile_preview = ProfileContributionPreview(
        manufacturer_directory=manufacturer_directory,
        model_directory=model_id,
        files=(),
    )
    branch_name = deterministic_branch(profile_preview, job_id or session_id) if eligible else ""
    commit_message = commit_message or f"feat(profile): add {manufacturer_directory} {model_id}"
    pr_title = pr_title or f"Add {manufacturer_directory} {model_id} power profile"
    file_lines = "\n".join(f"- `{file.path}`" for file in files) or "- None"
    controller = request.controller
    controller_data = controller.model_dump(mode="json") if controller is not None else {}
    controlled_entity = controller_data.get("entity_id")
    device_info: dict[str, str | int | float | bool | None] = {
        "manufacturer": manufacturer_name,
        "model_id": model_id,
        "product_name": product_name,
        "measure_device": request.measure_device,
    }
    home_assistant_info: dict[str, str | int | float | bool | None] = {
        "measure_type": request.measure_type.value,
        "controlled_entity": str(controlled_entity) if controlled_entity else None,
    }
    additional_info = notes or "Generated and validated by Powercalc Measure."
    default_pr_body = (
        "## Device information\n\n"
        f"- Manufacturer: {manufacturer_name}\n"
        f"- Model ID: {model_id}\n"
        f"- Product name: {product_name}\n"
        f"- Measurement device: {request.measure_device}\n\n"
        "## Home Assistant Device information\n\n"
        f"- Measure type: {request.measure_type.value}\n"
        f"- Controlled entity: {controlled_entity or 'Not available'}\n\n"
        "## Checklist\n\n"
        "- [x] I have created a single PR per device.\n"
        "- [x] For lights, only generated gzipped lookup tables are included.\n"
        "- [x] I reviewed the generated files and JSON in Powercalc Measure.\n\n"
        "## Additional info\n\n"
        f"{additional_info}\n\n"
        "### Generated files\n\n"
        f"{file_lines}\n"
    )
    pr_body = pr_body or default_pr_body
    return ContributionPreview(
        session_id=session_id,
        title=pr_title,
        body=pr_body,
        eligible=eligible,
        reason=reason,
        repository=repository.full_name,
        fork_repository=f"{fork_owner}/{repository.name}" if fork_owner else None,
        base_branch=repository.branch,
        default_branch=repository.branch,
        base_sha=base_sha,
        manufacturer_name=manufacturer_name,
        manufacturer_directory=manufacturer_directory,
        model_id=model_id,
        product_name=product_name,
        contributor=contributor,
        device_info=device_info,
        home_assistant=home_assistant_info,
        notes=notes,
        files=files,
        commit_message=commit_message,
        pr_title=pr_title,
        pr_body=pr_body,
        branch_name=branch_name,
        model_json=next(
            (file.rendered_json for file in files if file.path.endswith("/model.json")),
            None,
        ),
        metadata={
            "job_id": job_id,
            "base_sha": base_sha,
            "measure_type": request.measure_type.value,
            "model_id": model_id,
            "product_name": product_name,
            "measure_device": request.measure_device,
        },
        warnings=warnings,
    )


def _draft_files(artifact_root: Path) -> list[ContributionFile]:
    if not artifact_root.is_dir():
        return []
    return [
        ContributionFile(name=path.name, path=path.name, size=path.stat().st_size, media_type=None)
        for path in sorted(artifact_root.iterdir())
        if path.is_file() and not path.is_symlink()
    ]


def _preview_file(path: str, content: bytes) -> ContributionFile:
    rendered_json: Any | None = None
    text: str | None = None
    if path.endswith(".json"):
        rendered_json = json.loads(content)
    elif not path.endswith((".gz", ".png")):
        text = content.decode("utf-8")
    return ContributionFile(
        name=Path(path).name,
        path=path,
        size=len(content),
        media_type=None,
        content=text,
        rendered_json=rendered_json,
    )


def _preview_request_values(value: ContributionPreview | ContributionPreviewRequest) -> tuple[str, ...]:
    return (
        value.manufacturer_name,
        value.manufacturer_directory or "",
        value.model_id,
        value.product_name,
        value.contributor,
        value.notes,
    )


def _validate_latest_preview(
    job: ContributionJob,
    latest_preview: ProfileContributionPreview,
    base_sha: str,
) -> None:
    if job.base_sha != base_sha:
        raise ContributionError(
            ContributionErrorCode.SUBMISSION_FAILED,
            "Powercalc master changed after preview; refresh the preview before submitting",
        )
    if latest_preview != job.preview:
        raise ContributionError(
            ContributionErrorCode.SUBMISSION_FAILED,
            "Generated contribution files changed after preview; refresh the preview before submitting",
        )
