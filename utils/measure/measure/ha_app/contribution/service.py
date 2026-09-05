from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Literal

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
    DeviceInfo,
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
    DeviceFlowStart,
)
from measure.model import mains_voltage_from_range
from measure.profile.output import prepared_profile_archive
from measure.request import MeasurementRequest

MODEL_FILENAME = "model.json"


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

    def start_device_flow(self, client_id: str) -> DeviceFlowStart:
        try:
            data = GitHubClient().start_device_flow(client_id, REQUIRED_OAUTH_SCOPES)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, str(error)) from error
        complete_uri = data.get("verification_uri_complete")
        return DeviceFlowStart(
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
        if oauth_error == "authorization_pending":
            return DeviceFlowPollResponse(
                status="pending",
                message=str(data.get("error_description") or "Authorization pending"),
            )
        if oauth_error == "slow_down":
            return DeviceFlowPollResponse(
                status="slow_down",
                message=str(data.get("error_description") or "Authorization pending"),
                retry_after=_positive_integer(data.get("interval")),
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
        # Record what GitHub actually granted. Claiming the required scopes here would
        # mark the credential verified while submission later fails on a missing scope.
        granted = user.scopes or response_scopes
        self._credential_store.save(
            StoredCredential(
                kind="oauth",
                token=token,
                github_username=user.login,
                scopes=granted,
                permissions_verified=not missing_required_scopes(granted),
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
        integration: str | None = None,
    ) -> ContributionPreviewResponse:
        credential = self._credential_store.load()
        client = GitHubClient(credential.token if credential is not None else None)
        try:
            preparer, base_sha = self._build_reference_preparer(client)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.SUBMISSION_FAILED, str(error)) from error
        metadata = _metadata_from_request(request, payload, self.auth_status(), integration)
        try:
            job = self._build_coordinator(preparer, client).create_job(artifact_root, metadata, base_sha=base_sha)
        except ProfilePreparationError as error:
            code = (
                ContributionApiErrorCode.INVALID_METADATA
                if error.field
                else ContributionApiErrorCode.ARTIFACTS_REQUIRED
            )
            raise ContributionApiError(code, str(error), field=error.field) from error
        contents = preparer.render_contents(artifact_root, metadata, job.preview)
        self._save_prepared_archive(job.id, contents)
        return _preview_from_job(
            session_id=session_id,
            request=request,
            job=job,
            notes=payload.notes if payload is not None else "",
            contents=contents,
            base_sha=base_sha,
            fork_owner=credential.github_username if credential is not None else None,
            repository=client.repository,
        )

    def prepared_archive(self, job_id: str) -> bytes:
        """Return the exact profile package rendered for a persisted preview."""

        try:
            self._job_store.load(job_id)
        except KeyError, ValueError:
            raise ContributionApiError(
                ContributionApiErrorCode.PREVIEW_REQUIRED,
                "Profile preview expired; refresh the preview before downloading",
            ) from None
        path = self._prepared_archive_path(job_id)
        if not path.is_file():
            raise ContributionApiError(
                ContributionApiErrorCode.PREVIEW_REQUIRED,
                "Prepared profile expired; refresh the preview before downloading",
            )
        return path.read_bytes()

    def _save_prepared_archive(self, job_id: str, contents: tuple[tuple[str, bytes], ...]) -> None:
        directory = self._contribution_root / "prepared"
        directory.mkdir(parents=True, exist_ok=True)
        path = self._prepared_archive_path(job_id)
        archive = prepared_profile_archive(contents)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=f".{job_id}.", delete=False) as file:
            temporary = Path(file.name)
            file.write(archive)
        try:
            temporary.replace(path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        for existing in directory.glob("*.zip"):
            if existing != path:
                existing.unlink(missing_ok=True)

    def _prepared_archive_path(self, job_id: str) -> Path:
        # The job store validates identifiers before this path is used.
        return self._contribution_root / "prepared" / f"{job_id}.zip"

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
            code = (
                ContributionApiErrorCode.INVALID_METADATA
                if error.field
                else ContributionApiErrorCode.ARTIFACTS_REQUIRED
            )
            raise ContributionApiError(code, str(error), field=error.field) from error
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


def _positive_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdecimal():
            parsed = int(stripped)
            return parsed if parsed > 0 else None
    return None


@dataclass(frozen=True)
class _RequestMetadata:
    manufacturer: str
    model_id: str
    product_name: str | None
    contributor: str
    github_username: str | None
    contributor_email: str | None
    notes: str


def _request_metadata_values(
    request: MeasurementRequest,
    payload: ContributionPreviewRequest | None,
    auth: ContributionAuthStatus,
) -> _RequestMetadata:
    if payload is None:
        return _RequestMetadata(
            manufacturer="Unknown",
            model_id=request.model_id,
            product_name=request.product_name,
            contributor=auth.username or "",
            github_username=auth.username,
            contributor_email=None,
            notes="",
        )
    return _RequestMetadata(
        manufacturer=payload.manufacturer_name,
        model_id=payload.model_id,
        product_name=payload.product_name,
        contributor=payload.contributor,
        github_username=payload.contributor_github or auth.username,
        contributor_email=payload.contributor_email,
        notes=payload.notes,
    )


def _metadata_from_request(
    request: MeasurementRequest,
    payload: ContributionPreviewRequest | None,
    auth: ContributionAuthStatus,
    integration: str | None = None,
) -> ContributionMetadata:
    values = _request_metadata_values(request, payload, auth)
    if not values.github_username:
        raise ContributionApiError(
            ContributionApiErrorCode.INVALID_METADATA,
            "Contributor GitHub username is required",
            field="contributor_github",
        )
    try:
        return ContributionMetadata(
            manufacturer=values.manufacturer,
            model_id=values.model_id,
            product_name=values.product_name,
            measure_type=request.measure_type.value,
            aliases=tuple(payload.aliases) if payload is not None else None,
            gtins=tuple(payload.gtins) if payload is not None else None,
            product_url=payload.product_url if payload is not None else None,
            mains_voltage=payload.mains_voltage if payload is not None else None,
            device_specs=payload.device_specs if payload is not None else None,
            measure_device=_requested_measure_device(request, payload),
            measure_device_firmware=payload.measure_device_firmware if payload is not None else None,
            measure_description=payload.measure_description if payload is not None else None,
            integration=integration,
            notes=values.notes,
            author=ContributionAuthor(
                name=values.contributor,
                github=values.github_username,
                email=values.contributor_email,
            ),
        )
    except ValidationError as error:
        first_location = error.errors()[0].get("loc", ())
        field = str(first_location[0]) if first_location else None
        # ProfileAuthor is validated before ContributionMetadata, so its error
        # locations are name/github/email, without an "author" prefix.
        field_names: dict[str, str] = {
            "name": "contributor",
            "github": "contributor_github",
            "email": "contributor_email",
            "manufacturer": "manufacturer_name",
        }
        if field is not None:
            field = field_names.get(field, field)
        raise ContributionApiError(
            ContributionApiErrorCode.INVALID_METADATA,
            str(error.errors()[0]["msg"]).removeprefix("Value error, "),
            field=field,
        ) from error


def _requested_measure_device(
    request: MeasurementRequest,
    payload: ContributionPreviewRequest | None,
) -> str:
    if payload is None:
        return request.measure_device
    return payload.measure_device or request.measure_device


@dataclass(frozen=True)
class _PreviewContent:
    """The preview fields that differ between a placeholder draft and a prepared job."""

    manufacturer_name: str
    manufacturer_directory: str
    manufacturer_library_url: str | None
    model_id: str
    product_name: str
    contributor: str
    contributor_github: str
    contributor_email: str
    aliases: list[str]
    gtins: list[str]
    product_url: str
    mains_voltage: Literal[120, 230] | None
    voltage_range: dict[str, float] | None
    device_specs: dict[str, Any] | None
    device_type: str
    measure_device: str
    measure_device_firmware: str
    measure_description: str
    integration: str | None
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
    integration: str | None = None,
    manufacturer: str | None = None,
    default_model_id: str | None = None,
    default_measure_device_firmware: str | None = None,
    default_contributor_name: str | None = None,
    default_contributor_github: str | None = None,
    default_contributor_email: str | None = None,
) -> ContributionPreviewResponse:
    """Build a placeholder preview, before a contribution job exists."""
    files = _list_draft_files(artifact_root)
    reason = _contribution_ineligibility_reason(request, artifact_root, files)
    artifact_model = _artifact_model(artifact_root)
    voltage_range = _voltage_range(artifact_model)
    author = _first_author(artifact_model)
    content = _PreviewContent(
        manufacturer_name=manufacturer or "",
        manufacturer_directory="",
        manufacturer_library_url=None,
        model_id=request.model_id or default_model_id or "",
        product_name=request.product_name,
        contributor=str(author.get("name") or default_contributor_name or auth.username or ""),
        contributor_github=str(author.get("github") or default_contributor_github or auth.username or ""),
        contributor_email=str(author.get("email") or default_contributor_email or ""),
        aliases=_string_list(artifact_model.get("aliases")),
        gtins=_string_list(artifact_model.get("ean")),
        product_url=str(artifact_model.get("product_url") or ""),
        mains_voltage=_model_mains_voltage(artifact_model),
        voltage_range=voltage_range,
        device_specs=_artifact_device_specs(artifact_model),
        device_type=str(artifact_model.get("device_type") or ""),
        measure_device=str(artifact_model.get("measure_device") or request.measure_device),
        measure_device_firmware=str(
            artifact_model.get("measure_device_firmware") or default_measure_device_firmware or ""
        ),
        measure_description=str(artifact_model.get("measure_description") or ""),
        integration=integration,
        commit_message=f"feat(profile): add {request.model_id}",
        pr_title=f"Add {request.model_id} power profile",
        pr_body=profile_pull_request_body(
            DeviceInfo(
                manufacturer=manufacturer or "Unknown",
                model_id=request.model_id,
                product_name=request.product_name,
                integration=integration,
            ),
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


def _contribution_ineligibility_reason(
    request: MeasurementRequest,
    artifact_root: Path,
    files: list[ContributionFile],
) -> str | None:
    if request.measure_type not in SUPPORTED_MEASURE_TYPES:
        return "Automatic contribution is available for light, speaker, fan, and charging profiles"
    has_model = artifact_root.is_dir() and any(Path(file.path).name == MODEL_FILENAME for file in files)
    return None if has_model else f"Contribution requires a generated {MODEL_FILENAME} artifact"


def _artifact_device_specs(model: dict[str, Any]) -> dict[str, Any] | None:
    value = model.get("device_specs")
    return value if isinstance(value, dict) else None


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
    prepared_model = _prepared_model(contents)
    content = _PreviewContent(
        manufacturer_name=job.metadata.manufacturer,
        manufacturer_directory=job.preview.manufacturer_directory,
        manufacturer_library_url=job.preview.manufacturer_library_url,
        model_id=job.metadata.model_id,
        product_name=job.metadata.product_name or request.product_name,
        contributor=job.metadata.author.name,
        contributor_github=job.metadata.author.github,
        contributor_email=job.metadata.author.email or "",
        aliases=list(job.metadata.aliases or ()),
        gtins=list(job.metadata.gtins or ()),
        product_url=job.metadata.product_url or "",
        mains_voltage=_model_mains_voltage(prepared_model),
        voltage_range=_voltage_range(prepared_model),
        device_specs=job.metadata.device_specs,
        device_type=str(prepared_model.get("device_type") or ""),
        measure_device=job.metadata.measure_device or request.measure_device,
        measure_device_firmware=job.metadata.measure_device_firmware or "",
        measure_description=job.metadata.measure_description or "",
        integration=job.metadata.integration,
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
    device_info: dict[str, str | int | float | bool | None] = {
        "manufacturer": content.manufacturer_name,
        "model_id": content.model_id,
        "product_name": content.product_name,
        "measure_device": content.measure_device,
    }
    home_assistant_info: dict[str, str | int | float | bool | None] = {
        "measure_type": request.measure_type.value,
        "controlled_entity": ", ".join(request.controlled_entity_ids) or None,
        "integration": content.integration,
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
        manufacturer_library_url=content.manufacturer_library_url,
        model_id=content.model_id,
        product_name=content.product_name,
        contributor=content.contributor,
        contributor_github=content.contributor_github,
        contributor_email=content.contributor_email,
        aliases=content.aliases,
        gtins=content.gtins,
        product_url=content.product_url,
        mains_voltage=content.mains_voltage,
        voltage_range=content.voltage_range,
        device_specs=content.device_specs,
        device_type=content.device_type,
        measure_device=content.measure_device,
        measure_device_firmware=content.measure_device_firmware,
        measure_description=content.measure_description,
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
            (file.rendered_json for file in files if Path(file.path).name == MODEL_FILENAME),
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


def _artifact_model(artifact_root: Path) -> dict[str, Any]:
    try:
        value = json.loads((artifact_root / MODEL_FILENAME).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _voltage_range(model: dict[str, Any]) -> dict[str, float] | None:
    value = model.get("voltage_range")
    if not isinstance(value, dict):
        return None
    minimum = value.get("min")
    maximum = value.get("max")
    if (
        isinstance(minimum, bool)
        or isinstance(maximum, bool)
        or not isinstance(minimum, int | float)
        or not isinstance(maximum, int | float)
        or minimum > maximum
    ):
        return None
    return {"min": float(minimum), "max": float(maximum)}


def _model_mains_voltage(model: dict[str, Any]) -> Literal[120, 230] | None:
    derived = mains_voltage_from_range(model.get("voltage_range"))
    if derived is not None:
        return derived
    value = model.get("mains_voltage")
    if isinstance(value, bool) or value not in (120, 230):
        return None
    return 120 if value == 120 else 230


def _prepared_model(contents: tuple[tuple[str, bytes], ...]) -> dict[str, Any]:
    content = next((content for path, content in contents if Path(path).name == MODEL_FILENAME), None)
    if content is None:
        return {}
    try:
        value = json.loads(content)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _first_author(model: dict[str, Any]) -> dict[str, Any]:
    authors = model.get("authors")
    if isinstance(authors, list) and authors and isinstance(authors[0], dict):
        return authors[0]
    return {}


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


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
