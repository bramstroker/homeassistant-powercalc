from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from pydantic import SecretStr, ValidationError

from measure.contribution.coordinator import (
    ContributionCoordinator as ProfileContributionCoordinator,
    ContributionJobExpiredError,
    ContributionJobStore,
    conventional_commit_message,
    deterministic_branch,
    human_pull_request_title,
    profile_pull_request_body,
    pull_request_body,
)
from measure.contribution.credentials import CredentialStore, StoredCredential
from measure.contribution.github import (
    REQUIRED_OAUTH_SCOPES,
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
            user = GitHubClient(raw_token).validate_user()
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        repository_access_granted = bool({"repo", "public_repo"}.intersection(user.scopes))
        permission_granted = repository_access_granted and "workflow" in user.scopes
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
            user = GitHubClient(token).validate_user()
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
        credential = self._credential_store.load()
        if credential is None:
            raise ContributionApiError(
                ContributionApiErrorCode.AUTH_UNAVAILABLE,
                "Connect GitHub before building a contribution preview",
            )
        client = GitHubClient(credential.token)
        try:
            preparer, base_sha = self._reference_preparer(client)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.SUBMISSION_FAILED, str(error)) from error
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
            raise ContributionApiError(ContributionApiErrorCode.ARTIFACTS_REQUIRED, str(error)) from error
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
        preview: ContributionPreviewResponse,
        artifact_root: Path,
    ) -> ContributionSubmissionResult:
        job_id = preview.metadata.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise ContributionApiError(
                ContributionApiErrorCode.PREVIEW_REQUIRED,
                "Preview the current session before submitting it",
            )
        credential = self._credential_store.load()
        if credential is None:
            raise ContributionApiError(
                ContributionApiErrorCode.AUTH_UNAVAILABLE,
                "Connect GitHub before submitting a contribution",
            )
        client = GitHubClient(credential.token)
        try:
            preparer, base_sha = self._reference_preparer(client)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.SUBMISSION_FAILED, str(error)) from error
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
        coordinator = ProfileContributionCoordinator(
            preparer=preparer,
            credential_store=self._credential_store,
            job_store=self._job_store,
            github_client=client,
        )
        try:
            job = coordinator.submit(job_id, artifact_root)
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
    contributor = payload.contributor if payload is not None else auth.username or "Powercalc user"
    manufacturer = payload.manufacturer_name if payload is not None else "Unknown"
    model_id = payload.model_id if payload is not None else request.model_id
    manufacturer_directory = payload.manufacturer_directory if payload is not None else None
    try:
        return ContributionMetadata(
            manufacturer=manufacturer,
            manufacturer_directory=manufacturer_directory or None,
            model_id=model_id,
            product_name=payload.product_name if payload is not None else request.product_name,
            measure_type=request.measure_type.value,
            measure_device=request.measure_device,
            notes=payload.notes if payload is not None else "",
            author=ContributionAuthor(name=contributor, github=github_username),
        )
    except ValidationError as error:
        raise ContributionApiError(ContributionApiErrorCode.INVALID_METADATA, _validation_message(error)) from error


def _validation_message(error: ValidationError) -> str:
    issues = "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'value'}: {item['msg']}" for item in error.errors()
    )
    return f"Contribution details are invalid — {issues}"


def _draft_from_request(
    *,
    session_id: str,
    request: MeasurementRequest,
    artifact_root: Path,
    auth: ContributionAuthStatus,
) -> ContributionPreviewResponse:
    files = _draft_files(artifact_root)
    supported = request.measure_type in SUPPORTED_MEASURE_TYPES
    has_model = artifact_root.is_dir() and any(Path(file.path).name == "model.json" for file in files)
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
        files=files,
        eligible=eligible,
        reason=reason,
        contributor=auth.username or "",
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
    return _preview_response(
        session_id=session_id,
        request=request,
        files=[_preview_file(file.path, content_by_path[file.path]) for file in job.preview.files],
        eligible=True,
        reason=None,
        job=job,
        notes=notes,
        base_sha=base_sha,
        fork_owner=fork_owner,
        repository=repository,
    )


def _preview_response(
    *,
    session_id: str,
    request: MeasurementRequest,
    files: list[ContributionFile],
    eligible: bool,
    reason: str | None,
    job: ContributionJob | None = None,
    contributor: str = "",
    notes: str = "",
    base_sha: str | None = None,
    fork_owner: str | None = None,
    repository: GitHubRepository | None = None,
) -> ContributionPreviewResponse:
    repository = repository or GitHubRepository.from_environment()
    if job is not None:
        manufacturer_name = job.metadata.manufacturer
        manufacturer_directory = job.preview.manufacturer_directory
        model_id = job.metadata.model_id
        product_name = job.metadata.product_name or request.product_name
        contributor = job.metadata.author.name
        warnings = list(job.preview.warnings)
        commit_message = conventional_commit_message(job.preview)
        pr_title = human_pull_request_title(job.preview)
        pr_body = pull_request_body(job)
        branch_name = deterministic_branch(job.preview)
        job_id: str | None = job.id
    else:
        manufacturer_name = ""
        manufacturer_directory = ""
        model_id = request.model_id
        product_name = request.product_name
        warnings = []
        subject = " ".join(part for part in (manufacturer_directory, model_id) if part)
        commit_message = f"feat(profile): add {subject}"
        pr_title = f"Add {subject} power profile"
        pr_body = profile_pull_request_body(
            manufacturer=manufacturer_name or "Unknown",
            model_id=model_id,
            product_name=product_name,
            measure_device=request.measure_device,
            measure_type=request.measure_type.value,
            notes=notes,
            file_paths=[file.path for file in files],
        )
        branch_name = ""
        job_id = None
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
    return ContributionPreviewResponse(
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
            (file.rendered_json for file in files if Path(file.path).name == "model.json"),
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
