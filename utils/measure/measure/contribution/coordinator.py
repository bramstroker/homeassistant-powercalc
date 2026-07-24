from __future__ import annotations

import base64
from collections.abc import Sequence
import json
from pathlib import Path
from uuid import uuid4

from measure.clock import utc_now
from measure.contribution.credentials import CredentialStore
from measure.contribution.files import write_json_atomic
from measure.contribution.github import REQUIRED_OAUTH_SCOPES, GitHubApiError, GitHubClient
from measure.contribution.models import (
    ContributionError,
    ContributionErrorCode,
    ContributionJob,
    ContributionJobStatus,
    ContributionMetadata,
    ContributionSubmission,
)
from measure.contribution.pr_text import (
    conventional_commit_message,
    deterministic_branch_name,
    pull_request_body,
    pull_request_title,
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


class ContributionJobCoordinator:
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
        now = utc_now()
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
            return self._fail(job, ContributionErrorCode.MISSING_CREDENTIALS, "GitHub credentials are required")
        client = self.github_client or GitHubClient(credential.token)
        submitting = self._transition(job, ContributionJobStatus.SUBMITTING)
        try:
            submission = self._submit_to_github(client, submitting, artifact_directory)
        except (GitHubApiError, KeyError, ValueError, OSError) as error:
            return self._fail(submitting, ContributionErrorCode.GITHUB_ERROR, str(error))
        return self._transition(submitting, ContributionJobStatus.SUBMITTED, submission=submission, error=None)

    def _submit_to_github(
        self,
        client: GitHubClient,
        job: ContributionJob,
        artifact_directory: Path,
    ) -> ContributionSubmission:
        user = client.fetch_authenticated_user()
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
        branch = deterministic_branch_name(job.preview)
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
        for path, content in self.preparer.render_contents(artifact_directory, job.metadata, job.preview):
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
            title=pull_request_title(job.preview),
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

    def _transition(self, job: ContributionJob, status: ContributionJobStatus, **updates: object) -> ContributionJob:
        return self.job_store.save(
            job.model_copy(update={"status": status, "updated_at": utc_now(), **updates}),
        )

    def _fail(self, job: ContributionJob, code: ContributionErrorCode, message: str) -> ContributionJob:
        return self._transition(job, ContributionJobStatus.FAILED, error=ContributionError(code=code, message=message))
