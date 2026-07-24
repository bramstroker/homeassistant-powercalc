from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any

from pydantic import SecretStr, ValidationError

from measure.contribution.coordinator import (
    ContributionJobCoordinator,
    ContributionJobExpiredError,
    ContributionJobStore,
)
from measure.contribution.credentials import CredentialStore, StoredCredential
from measure.contribution.github import (
    REQUIRED_OAUTH_SCOPES,
    GitHubApiError,
    GitHubClient,
    GitHubRepository,
    missing_required_scopes,
)
from measure.contribution.models import (
    ContributionAuthor,
    ContributionJob,
    ContributionMetadata,
    ContributionPreview as ProfileContributionPreview,
)
from measure.contribution.prepare import ProfilePreparationError, ProfilePreparer
from measure.contribution.pull_request import (
    conventional_commit_message,
    deterministic_branch_name,
    profile_pull_request_body,
    pull_request_body,
    pull_request_title,
)
from measure.ha_app.contribution.models import (
    SUPPORTED_MEASURE_TYPES,
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionAuthMethod,
    ContributionAuthStatus,
    ContributionFile,
    ContributionIdentity,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
    ContributionService,
    ContributionSubmissionResult,
    DeviceFlowPollResponse,
    DeviceFlowStartResponse,
)
from measure.request import MeasurementRequest


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
            user = GitHubClient(raw_token).fetch_authenticated_user()
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        permission_granted = not missing_required_scopes(user.scopes)
        if user.scopes_reported and not permission_granted:
            raise ContributionApiError(
                ContributionApiErrorCode.AUTH_UNAVAILABLE,
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
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        complete_uri = data.get("verification_uri_complete")
        # flow_id is assigned by the API coordinator; the device code must never
        # reach clients (only the excluded device_code field may carry it).
        return DeviceFlowStartResponse(
            flow_id=None,
            device_code=str(data["device_code"]),
            user_code=str(data["user_code"]),
            verification_uri=str(data["verification_uri"]),
            verification_uri_complete=str(complete_uri) if complete_uri is not None else None,
            expires_in=int(data["expires_in"]),
            interval=int(data["interval"]),
            message=f"Enter code {data['user_code']} at {data['verification_uri']}",
        )

    def poll_device_flow(self, client_id: str, device_code: str) -> DeviceFlowPollResponse:
        try:
            data = GitHubClient().poll_device_flow(client_id, device_code)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(error)) from error
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
            raise ContributionApiError(
                ContributionApiErrorCode.AUTH_UNAVAILABLE,
                "GitHub Device Flow did not return an access token",
            )
        try:
            user = GitHubClient(token).fetch_authenticated_user()
        except GitHubApiError as auth_error:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(auth_error)) from auth_error
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
    ) -> ContributionPreviewResponse:
        credential, client, preparer, base_sha = self._load_github_context("building a contribution preview")
        metadata = _metadata_from_request(request, payload, self.auth_status())
        try:
            job = self._build_coordinator(preparer, client).create_job(artifact_root, metadata, base_sha=base_sha)
        except ProfilePreparationError as error:
            raise ContributionApiError(ContributionApiErrorCode.ARTIFACTS_REQUIRED, str(error)) from error
        contents = preparer.render_contents(artifact_root, metadata, job.preview)
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
        preview: ContributionPreviewResponse,
        artifact_root: Path,
    ) -> ContributionSubmissionResult:
        job_id = preview.job_id
        if not job_id:
            raise ContributionApiError(
                ContributionApiErrorCode.PREVIEW_REQUIRED,
                "Preview the current session before submitting it",
            )
        _credential, client, preparer, base_sha = self._load_github_context("submitting a contribution")
        try:
            job_before_submit = self._job_store.load(job_id)
        except KeyError:
            raise ContributionApiError(
                ContributionApiErrorCode.PREVIEW_REQUIRED,
                "Contribution preview expired; refresh the preview before submitting",
            ) from None
        try:
            latest_preview = preparer.prepare(artifact_root, job_before_submit.metadata)
        except ProfilePreparationError as error:
            raise ContributionApiError(ContributionApiErrorCode.ARTIFACTS_REQUIRED, str(error)) from error
        _validate_latest_preview(job_before_submit, latest_preview, base_sha)
        try:
            job = self._build_coordinator(preparer, client).submit(job_id, artifact_root)
        except ContributionJobExpiredError as error:
            raise ContributionApiError(ContributionApiErrorCode.PREVIEW_REQUIRED, str(error)) from error
        if job.error is not None:
            raise ContributionApiError(ContributionApiErrorCode.SUBMISSION_FAILED, job.error.message)
        if job.submission is None:
            raise ContributionApiError(
                ContributionApiErrorCode.SUBMISSION_FAILED,
                "Contribution submission did not return a pull request",
            )
        return ContributionSubmissionResult(
            pull_request_url=job.submission.pull_request_url,
            repository=client.repository.full_name,
            branch_name=job.submission.branch,
            message="Contribution submitted",
        )

    def _load_github_context(self, action: str) -> tuple[StoredCredential, GitHubClient, ProfilePreparer, str]:
        """Load the stored credential and build a preparer pinned to the current upstream sha."""
        credential = self._credential_store.load()
        if credential is None:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, f"Connect GitHub before {action}")
        client = GitHubClient(credential.token)
        try:
            preparer, base_sha = self._build_reference_preparer(client)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.SUBMISSION_FAILED, str(error)) from error
        return credential, client, preparer, base_sha

    def _build_coordinator(self, preparer: ProfilePreparer, client: GitHubClient) -> ContributionJobCoordinator:
        return ContributionJobCoordinator(
            preparer=preparer,
            credential_store=self._credential_store,
            job_store=self._job_store,
            github_client=client,
        )

    def _build_reference_preparer(self, client: GitHubClient) -> tuple[ProfilePreparer, str]:
        repository = client.repository
        base_ref = client.get_ref(repository.owner, repository.name, repository.branch)
        if base_ref is None:
            raise ContributionApiError(
                ContributionApiErrorCode.SUBMISSION_FAILED,
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


def create_contribution_service(data_root: Path) -> ContributionService:
    return SharedContributionService(data_root)


def _metadata_from_request(
    request: MeasurementRequest,
    payload: ContributionPreviewRequest | None,
    auth: ContributionAuthStatus,
) -> ContributionMetadata:
    github_username = auth.username
    if not github_username:
        raise ContributionApiError(
            ContributionApiErrorCode.AUTH_UNAVAILABLE,
            "Connected GitHub account has no username",
        )
    if payload is not None:
        manufacturer = payload.manufacturer_name
        manufacturer_directory = payload.manufacturer_directory or None
        model_id = payload.model_id
        product_name: str | None = payload.product_name
        contributor = payload.contributor
        notes = payload.notes
    else:
        manufacturer = "Unknown"
        manufacturer_directory = None
        model_id = request.model_id
        product_name = request.product_name
        contributor = github_username
        notes = ""
    try:
        return ContributionMetadata(
            manufacturer=manufacturer,
            manufacturer_directory=manufacturer_directory,
            model_id=model_id,
            product_name=product_name,
            measure_type=request.measure_type.value,
            measure_device=request.measure_device,
            notes=notes,
            author=ContributionAuthor(name=contributor, github=github_username),
        )
    except ValidationError as error:
        raise ContributionApiError(ContributionApiErrorCode.INVALID_METADATA, _validation_message(error)) from error


def _validation_message(error: ValidationError) -> str:
    issues = "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'value'}: {item['msg']}" for item in error.errors()
    )
    return f"Contribution details are invalid — {issues}"


@dataclass(frozen=True)
class _PreviewContent:
    """The preview fields that differ between a placeholder draft and a prepared job."""

    manufacturer_name: str
    manufacturer_directory: str
    model_id: str
    product_name: str
    contributor: str
    commit_message: str
    pr_title: str
    pr_body: str
    branch_name: str
    job_id: str | None
    warnings: list[str]


def draft_from_request(
    *,
    session_id: str,
    request: MeasurementRequest,
    artifact_root: Path,
    auth: ContributionAuthStatus,
) -> ContributionPreviewResponse:
    """Build a placeholder preview, before a contribution job exists."""
    files = _list_draft_files(artifact_root)
    supported = request.measure_type in SUPPORTED_MEASURE_TYPES
    has_model = artifact_root.is_dir() and any(Path(file.path).name == "model.json" for file in files)
    if not supported:
        reason = "Automatic contribution is available for light, speaker, fan, and charging profiles"
    elif not has_model:
        reason = "Contribution requires a generated model.json artifact"
    else:
        reason = None
    content = _PreviewContent(
        manufacturer_name="",
        manufacturer_directory="",
        model_id=request.model_id,
        product_name=request.product_name,
        contributor=auth.username or "",
        commit_message=f"feat(profile): add {request.model_id}",
        pr_title=f"Add {request.model_id} power profile",
        pr_body=profile_pull_request_body(
            manufacturer="Unknown",
            model_id=request.model_id,
            product_name=request.product_name,
            measure_device=request.measure_device,
            measure_type=request.measure_type.value,
            notes="",
            file_paths=[file.path for file in files],
        ),
        branch_name="",
        job_id=None,
        warnings=[],
    )
    return _build_preview_response(
        session_id=session_id,
        request=request,
        files=files,
        eligible=reason is None,
        reason=reason,
        content=content,
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
) -> ContributionPreviewResponse:
    content_by_path = dict(contents)
    content = _PreviewContent(
        manufacturer_name=job.metadata.manufacturer,
        manufacturer_directory=job.preview.manufacturer_directory,
        model_id=job.metadata.model_id,
        product_name=job.metadata.product_name or request.product_name,
        contributor=job.metadata.author.name,
        commit_message=conventional_commit_message(job.preview),
        pr_title=pull_request_title(job.preview),
        pr_body=pull_request_body(job),
        branch_name=deterministic_branch_name(job.preview),
        job_id=job.id,
        warnings=list(job.preview.warnings),
    )
    return _build_preview_response(
        session_id=session_id,
        request=request,
        files=[_build_preview_file(file.path, content_by_path[file.path]) for file in job.preview.files],
        eligible=True,
        reason=None,
        content=content,
        notes=notes,
        base_sha=base_sha,
        fork_owner=fork_owner,
        repository=repository,
    )


def _build_preview_response(
    *,
    session_id: str,
    request: MeasurementRequest,
    files: list[ContributionFile],
    eligible: bool,
    reason: str | None,
    content: _PreviewContent,
    notes: str = "",
    base_sha: str | None = None,
    fork_owner: str | None = None,
    repository: GitHubRepository | None = None,
) -> ContributionPreviewResponse:
    repository = repository or GitHubRepository.from_environment()
    controller = request.controller
    controller_data = controller.model_dump(mode="json") if controller is not None else {}
    controlled_entity = controller_data.get("entity_id")
    device_info: dict[str, str | int | float | bool | None] = {
        "manufacturer": content.manufacturer_name,
        "model_id": content.model_id,
        "product_name": content.product_name,
        "measure_device": request.measure_device,
    }
    home_assistant_info: dict[str, str | int | float | bool | None] = {
        "measure_type": request.measure_type.value,
        "controlled_entity": str(controlled_entity) if controlled_entity else None,
    }
    return ContributionPreviewResponse(
        session_id=session_id,
        eligible=eligible,
        reason=reason,
        repository=repository.full_name,
        fork_repository=f"{fork_owner}/{repository.name}" if fork_owner else None,
        base_branch=repository.branch,
        base_sha=base_sha,
        manufacturer_name=content.manufacturer_name,
        manufacturer_directory=content.manufacturer_directory,
        model_id=content.model_id,
        product_name=content.product_name,
        contributor=content.contributor,
        device_info=device_info,
        home_assistant=home_assistant_info,
        notes=notes,
        files=files,
        commit_message=content.commit_message,
        pr_title=content.pr_title,
        pr_body=content.pr_body,
        branch_name=content.branch_name,
        job_id=content.job_id,
        model_json=next(
            (file.rendered_json for file in files if Path(file.path).name == "model.json"),
            None,
        ),
        warnings=content.warnings,
    )


def _list_draft_files(artifact_root: Path) -> list[ContributionFile]:
    if not artifact_root.is_dir():
        return []
    return [
        ContributionFile(name=path.name, path=path.name, size=path.stat().st_size)
        for path in sorted(artifact_root.iterdir())
        if path.is_file() and not path.is_symlink()
    ]


def _build_preview_file(path: str, content: bytes) -> ContributionFile:
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
        content=text,
        rendered_json=rendered_json,
    )


def _validate_latest_preview(
    job: ContributionJob,
    latest_preview: ProfileContributionPreview,
    base_sha: str,
) -> None:
    if job.base_sha != base_sha:
        raise ContributionApiError(
            ContributionApiErrorCode.PREVIEW_REQUIRED,
            "Powercalc master changed after preview; refresh the preview before submitting",
        )
    if latest_preview != job.preview:
        raise ContributionApiError(
            ContributionApiErrorCode.PREVIEW_REQUIRED,
            "Generated contribution files changed after preview; refresh the preview before submitting",
        )
