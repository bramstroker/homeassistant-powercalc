from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile

from pydantic import SecretStr

from measure.contribution.coordinator import (
    ContributionJobCoordinator,
    ContributionJobExpiredError,
    ContributionJobStore,
)
from measure.contribution.credentials import CredentialStore
from measure.contribution.github import (
    GitHubApiError,
    GitHubClient,
)
from measure.contribution.models import ContributionJob
from measure.ha_app.contribution.auth import ContributionAuth
from measure.ha_app.contribution.models import (
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionAuthStatus,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
    ContributionService,
    ContributionSubmissionResult,
    DeviceFlowPollResponse,
    DeviceFlowStart,
)
from measure.ha_app.contribution.preview import metadata_from_request, preview_from_job
from measure.profile.models import ProfilePreview, RenderedProfileFile
from measure.profile.output import prepared_profile_archive
from measure.profile.prepare import ProfilePreparationError, ProfilePreparer
from measure.request import MeasurementRequest


@dataclass(frozen=True)
class GitHubContext:
    """GitHub client and profile preparer pinned to an upstream revision."""

    client: GitHubClient
    preparer: ProfilePreparer
    base_sha: str


class SharedContributionService:
    def __init__(self, data_root: Path) -> None:
        self._contribution_root = data_root / "contribution"
        self._credential_store = CredentialStore(self._contribution_root / "credentials.json")
        self._auth = ContributionAuth(self._credential_store)
        self._job_store = ContributionJobStore(self._contribution_root / "jobs")

    def auth_status(self) -> ContributionAuthStatus:
        return self._auth.auth_status()

    def connect_pat(self, token: SecretStr) -> ContributionAuthStatus:
        return self._auth.connect_pat(token)

    def disconnect(self) -> ContributionAuthStatus:
        return self._auth.disconnect()

    def start_device_flow(self, client_id: str) -> DeviceFlowStart:
        return self._auth.start_device_flow(client_id)

    def poll_device_flow(self, client_id: str, device_code: str) -> DeviceFlowPollResponse:
        return self._auth.poll_device_flow(client_id, device_code)

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
            context = self._build_github_context(client)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.SUBMISSION_FAILED, str(error)) from error
        metadata = metadata_from_request(request, payload, self.auth_status(), integration)
        try:
            job = self._build_coordinator(context).create_job(artifact_root, metadata, base_sha=context.base_sha)
        except ProfilePreparationError as error:
            code = (
                ContributionApiErrorCode.INVALID_METADATA
                if error.field
                else ContributionApiErrorCode.ARTIFACTS_REQUIRED
            )
            raise ContributionApiError(code, str(error), field=error.field) from error
        contents = context.preparer.render_contents(artifact_root, metadata, job.preview)
        self._save_prepared_archive(job.id, contents)
        return preview_from_job(
            session_id=session_id,
            request=request,
            job=job,
            notes=payload.notes if payload is not None else "",
            contents=contents,
            base_sha=context.base_sha,
            fork_owner=credential.github_username if credential is not None else None,
            repository=context.client.repository,
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

    def _save_prepared_archive(self, job_id: str, contents: list[RenderedProfileFile]) -> None:
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
        context = self._load_github_context("submitting a contribution")
        try:
            job_before_submit = self._job_store.load(job_id)
        except KeyError:
            raise ContributionApiError(
                ContributionApiErrorCode.PREVIEW_REQUIRED,
                "Contribution preview expired; refresh the preview before submitting",
            ) from None
        try:
            latest_preview = context.preparer.prepare(artifact_root, job_before_submit.metadata)
        except ProfilePreparationError as error:
            code = (
                ContributionApiErrorCode.INVALID_METADATA
                if error.field
                else ContributionApiErrorCode.ARTIFACTS_REQUIRED
            )
            raise ContributionApiError(code, str(error), field=error.field) from error
        _validate_latest_preview(job_before_submit, latest_preview, context.base_sha)
        try:
            job = self._build_coordinator(context).submit(job_id, artifact_root)
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
            repository=context.client.repository.full_name,
            branch_name=job.submission.branch,
            message="Contribution submitted",
        )

    def _load_github_context(self, action: str) -> GitHubContext:
        """Load the stored credential and build a preparer pinned to the current upstream sha."""
        credential = self._credential_store.load()
        if credential is None:
            raise ContributionApiError(ContributionApiErrorCode.AUTH_UNAVAILABLE, f"Connect GitHub before {action}")
        client = GitHubClient(credential.token)
        try:
            context = self._build_github_context(client)
        except GitHubApiError as error:
            raise ContributionApiError(ContributionApiErrorCode.SUBMISSION_FAILED, str(error)) from error
        return context

    def _build_coordinator(self, context: GitHubContext) -> ContributionJobCoordinator:
        return ContributionJobCoordinator(
            preparer=context.preparer,
            credential_store=self._credential_store,
            job_store=self._job_store,
            github_client=context.client,
        )

    def _build_github_context(self, client: GitHubClient) -> GitHubContext:
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
        return GitHubContext(
            client=client,
            preparer=ProfilePreparer(library_root=library_root, model_schema_path=schema_path),
            base_sha=base_sha,
        )


def create_contribution_service(data_root: Path) -> ContributionService:
    return SharedContributionService(data_root)


def _validate_latest_preview(
    job: ContributionJob,
    latest_preview: ProfilePreview,
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
