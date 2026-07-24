from __future__ import annotations

import base64
from collections.abc import Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from measure.contribution.credentials import CredentialStore
from measure.contribution.files import write_json_atomic
from measure.contribution.github import REQUIRED_OAUTH_SCOPES, GitHubApiError, GitHubClient
from measure.contribution.models import (
    ContributionError,
    ContributionErrorCode,
    ContributionJob,
    ContributionJobStatus,
    ContributionMetadata,
    ContributionPreview,
    ContributionSubmission,
)
from measure.contribution.prepare import ProfilePreparer


class ContributionJobExpiredError(LookupError):
    """The referenced contribution job no longer exists; the preview must be refreshed."""


def _granted_scopes(scopes: Sequence[str]) -> set[str]:
    """The classic ``repo`` scope is a superset that implies ``public_repo``."""
    granted = set(scopes)
    if "repo" in granted:
        granted.add("public_repo")
    return granted


class ContributionJobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, job: ContributionJob) -> ContributionJob:
        write_json_atomic(self._path(job.id), job.model_dump(mode="json"))
        return job

    def load(self, job_id: str) -> ContributionJob:
        path = self._path(job_id)
        if not path.exists():
            raise KeyError(job_id)
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
        return ContributionJob.model_validate(value)

    def prune(self, keep_job_id: str) -> None:
        keep_path = self._path(keep_job_id)
        for path in self.root.glob("*.json"):
            if path != keep_path:
                path.unlink(missing_ok=True)

    def _path(self, job_id: str) -> Path:
        if not job_id or not job_id.replace("-", "").isalnum():
            raise ValueError("Invalid contribution job id")
        return self.root / f"{job_id}.json"


class ContributionCoordinator:
    def __init__(
        self,
        *,
        preparer: ProfilePreparer,
        credential_store: CredentialStore,
        job_store: ContributionJobStore,
        github_client: GitHubClient | None = None,
    ) -> None:
        self.preparer = preparer
        self.credential_store = credential_store
        self.job_store = job_store
        self.github_client = github_client

    def create_job(
        self,
        artifact_directory: Path,
        metadata: ContributionMetadata,
        *,
        base_sha: str | None = None,
    ) -> ContributionJob:
        preview = self.preparer.prepare(artifact_directory, metadata)
        now = _utc_now()
        job = self.job_store.save(
            ContributionJob(
                id=uuid4().hex,
                status=ContributionJobStatus.PREVIEWED,
                metadata=metadata,
                preview=preview,
                base_sha=base_sha,
                created_at=now,
                updated_at=now,
            ),
        )
        self.job_store.prune(job.id)
        return job

    def submit(self, job_id: str, artifact_directory: Path) -> ContributionJob:
        try:
            job = self.job_store.load(job_id)
        except KeyError:
            raise ContributionJobExpiredError(
                "Contribution preview expired; refresh the preview before submitting",
            ) from None
        if job.submission is not None:
            return job
        credential = self.credential_store.load()
        if credential is None:
            failed = self._fail(job, ContributionErrorCode.MISSING_CREDENTIALS, "GitHub credentials are required")
            return self.job_store.save(failed)
        client = self.github_client or GitHubClient(credential.token)
        submitting = job.model_copy(update={"status": ContributionJobStatus.SUBMITTING, "updated_at": _utc_now()})
        self.job_store.save(submitting)
        try:
            submission = self._submit_prepared(client, submitting, artifact_directory)
        except (GitHubApiError, KeyError, ValueError, OSError) as error:
            return self.job_store.save(self._fail(submitting, ContributionErrorCode.GITHUB_ERROR, str(error)))
        return self.job_store.save(
            submitting.model_copy(
                update={
                    "status": ContributionJobStatus.SUBMITTED,
                    "submission": submission,
                    "updated_at": _utc_now(),
                    "error": None,
                },
            ),
        )

    def _submit_prepared(
        self,
        client: GitHubClient,
        job: ContributionJob,
        artifact_directory: Path,
    ) -> ContributionSubmission:
        user = client.validate_user()
        repository = client.repository
        uses_fork = user.login.casefold() != repository.owner.casefold()
        missing_scopes = set(REQUIRED_OAUTH_SCOPES).difference(_granted_scopes(user.scopes))
        if uses_fork and user.scopes_reported and missing_scopes:
            scopes = " and ".join(sorted(missing_scopes))
            raise GitHubApiError(
                f"GitHub authorization is missing the {scopes} scope; disconnect and reconnect GitHub in Settings",
            )
        if not uses_fork:
            fork_owner = repository.owner
            fork_repo = repository.name
        else:
            fork = client.find_fork(user.login)
            if fork is None:
                fork = client.create_fork()
            fork_owner = str(fork["owner"]["login"])
            fork_repo = str(fork["name"])
        branch = deterministic_branch(job.preview)
        head = f"{fork_owner}:{branch}"
        base_ref = client.get_ref(repository.owner, repository.name, repository.branch)
        if base_ref is None:
            raise GitHubApiError("Upstream branch was not found")
        parent_sha = str(base_ref["object"]["sha"])
        if job.base_sha is not None and parent_sha != job.base_sha:
            raise GitHubApiError(
                f"{repository.full_name} {repository.branch} changed after preview; "
                "refresh the preview before submitting",
            )
        self._prepare_contribution_branch(
            client,
            fork_owner=fork_owner,
            fork_repo=fork_repo,
            branch=branch,
            base_branch=repository.branch,
            parent_sha=parent_sha,
            uses_fork=uses_fork,
        )
        parent_commit = client.get_commit(fork_owner, fork_repo, parent_sha)
        base_tree_sha = str(parent_commit["tree"]["sha"])

        tree_entries = []
        for path, content in self.preparer.prepared_contents(artifact_directory, job.metadata, job.preview):
            blob_sha = client.create_blob(fork_owner, fork_repo, base64.b64encode(content).decode("ascii"))
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})
        tree_sha = client.create_tree(fork_owner, fork_repo, base_tree_sha, tuple(tree_entries))
        commit_sha = client.create_commit(
            fork_owner,
            fork_repo,
            conventional_commit_message(job.preview),
            tree_sha,
            parent_sha,
        )
        # This branch is scoped to one device profile. Forcing the ref replaces a
        # commit from an interrupted submit and refreshes an already-open pull
        # request with the latest prepared files.
        client.update_ref(fork_owner, fork_repo, branch, commit_sha, force=True)
        existing_pull_request = client.find_pull_request(
            repository.owner,
            repository.name,
            head=head,
            base=repository.branch,
        )
        pull_request = existing_pull_request or client.create_pull_request(
            repository.owner,
            repository.name,
            title=human_pull_request_title(job.preview),
            head=head,
            base=repository.branch,
            body=pull_request_body(job),
        )
        return ContributionSubmission(
            branch=branch,
            commit_sha=commit_sha,
            pull_request_url=str(pull_request["html_url"]),
            pull_request_number=int(pull_request["number"]) if pull_request.get("number") is not None else None,
        )

    @staticmethod
    def _prepare_contribution_branch(
        client: GitHubClient,
        *,
        fork_owner: str,
        fork_repo: str,
        branch: str,
        base_branch: str,
        parent_sha: str,
        uses_fork: bool,
    ) -> None:
        contribution_ref = client.get_ref(fork_owner, fork_repo, branch)
        if not uses_fork:
            if contribution_ref is None:
                client.create_ref(fork_owner, fork_repo, branch, parent_sha)
            else:
                client.update_ref(fork_owner, fork_repo, branch, parent_sha, force=True)
            return

        fork_base_ref = client.get_ref(fork_owner, fork_repo, base_branch)
        if fork_base_ref is None:
            raise GitHubApiError("The fork base branch was not found")
        if contribution_ref is None:
            fork_base_sha = str(fork_base_ref["object"]["sha"])
            client.create_ref(fork_owner, fork_repo, branch, fork_base_sha)
        client.sync_fork_branch(fork_owner, fork_repo, branch)

    @staticmethod
    def _fail(job: ContributionJob, code: ContributionErrorCode, message: str) -> ContributionJob:
        return job.model_copy(
            update={
                "status": ContributionJobStatus.FAILED,
                "updated_at": _utc_now(),
                "error": ContributionError(code=code, message=message),
            },
        )


def deterministic_branch(preview: ContributionPreview) -> str:
    manufacturer = _branch_part(preview.manufacturer_directory)
    model = _branch_part(preview.model_directory)
    return f"powercalc-profile-{manufacturer}-{model}"


def conventional_commit_message(preview: ContributionPreview) -> str:
    return f"feat(profile): add {preview.manufacturer_directory} {preview.model_directory}"


def human_pull_request_title(preview: ContributionPreview) -> str:
    return f"Add {preview.manufacturer_directory} {preview.model_directory} power profile"


def pull_request_body(job: ContributionJob) -> str:
    return profile_pull_request_body(
        manufacturer=job.metadata.manufacturer,
        model_id=job.metadata.model_id,
        product_name=job.metadata.product_name or job.preview.model_directory,
        measure_device=job.metadata.measure_device,
        measure_type=job.metadata.measure_type,
        notes=job.metadata.notes,
        file_paths=[file.path for file in job.preview.files],
        warnings=job.preview.warnings,
    )


def profile_pull_request_body(
    *,
    manufacturer: str,
    model_id: str,
    product_name: str,
    measure_device: str | None,
    measure_type: str | None,
    notes: str,
    file_paths: Sequence[str],
    warnings: Sequence[str] = (),
) -> str:
    device_lines = [
        f"- Manufacturer: {manufacturer}",
        f"- Model ID: {model_id}",
        f"- Product name: {product_name}",
    ]
    if measure_device:
        device_lines.append(f"- Measurement device: {measure_device}")
    home_assistant = (
        f"- Measure type: {measure_type}\n"
        if measure_type
        else "Generated by Powercalc Measure from a completed measurement session.\n"
    )
    files = "\n".join(f"- `{path}`" for path in file_paths) or "- None"
    warning_lines = "\n".join(f"- {warning}" for warning in warnings) or "- None"
    additional_info = notes or "Generated and validated by Powercalc Measure."
    return (
        "## Device information\n\n"
        f"{'\n'.join(device_lines)}\n\n"
        "## Home Assistant Device information\n\n"
        f"{home_assistant}\n"
        "## Checklist\n\n"
        "- [x] I have created a single PR per device.\n"
        "- [x] For lights, only generated gzipped lookup tables are included.\n"
        "- [x] I reviewed the generated files and JSON in Powercalc Measure.\n\n"
        "## Additional info\n\n"
        f"{additional_info}\n\n"
        "### Generated files\n\n"
        f"{files}\n\n"
        "### Duplicate warnings\n\n"
        f"{warning_lines}\n"
    )


def _branch_part(value: str) -> str:
    normalized = "".join(character if character.isalnum() else "-" for character in value.lower())
    return "-".join(part for part in normalized.split("-") if part)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
