from __future__ import annotations

from pathlib import Path
from typing import Any

from measure.contribution.coordinator import ContributionCoordinator, ContributionJobStore
from measure.contribution.credentials import CredentialStore, StoredCredential
from measure.contribution.github import GitHubClient, GitHubRepository, GitHubUser
from measure.contribution.models import (
    ContributionAuthor,
    ContributionJob,
    ContributionMetadata,
    ContributionPreparedFile,
    ContributionPreview,
)
from measure.contribution.prepare import ProfilePreparer
from measure.ha_app.contribution import ContributionError, _validate_latest_preview
import pytest


class FakeGitHubClient(GitHubClient):
    def __init__(self, repository: GitHubRepository | None = None) -> None:
        super().__init__("token", repository=repository)
        self.calls: list[str] = []
        self.user = GitHubUser(login="octo", scopes=("public_repo", "workflow"), scopes_reported=True)

    def validate_user(self) -> GitHubUser:
        self.calls.append("validate_user")
        return self.user

    def find_fork(self, username: str, repo: str | None = None) -> dict[str, Any] | None:
        repo = repo or self.repository.name
        self.calls.append(f"find_fork:{username}:{repo}")
        return {"name": repo, "owner": {"login": username}}

    def get_ref(self, owner: str, repo: str, branch: str) -> dict[str, Any] | None:
        self.calls.append(f"get_ref:{owner}:{repo}:{branch}")
        return {"object": {"sha": "base-sha"}}

    def find_pull_request(self, owner: str, repo: str, *, head: str, base: str) -> dict[str, Any] | None:
        self.calls.append(f"find_pr:{head}:{base}")
        return None

    def get_commit(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        self.calls.append(f"get_commit:{sha}")
        return {"tree": {"sha": "base-tree-sha"}}

    def sync_fork_branch(self, owner: str, repo: str, branch: str) -> None:
        self.calls.append(f"sync_fork_branch:{owner}:{repo}:{branch}")

    def create_ref(self, owner: str, repo: str, branch: str, sha: str) -> dict[str, Any]:
        self.calls.append(f"create_ref:{branch}:{sha}")
        return {}

    def create_blob(self, owner: str, repo: str, content: str, *, encoding: str = "base64") -> str:
        self.calls.append(f"create_blob:{encoding}:{content[:8]}")
        return f"blob-{len(self.calls)}"

    def create_tree(
        self,
        owner: str,
        repo: str,
        base_tree: str,
        tree: tuple[dict[str, Any], ...],
    ) -> str:
        self.calls.append(f"create_tree:{base_tree}:{len(tree)}")
        return "tree-sha"

    def create_commit(self, owner: str, repo: str, message: str, tree_sha: str, parent_sha: str) -> str:
        self.calls.append(f"create_commit:{message}:{tree_sha}:{parent_sha}")
        return "commit-sha"

    def update_ref(self, owner: str, repo: str, branch: str, sha: str, *, force: bool = False) -> dict[str, Any]:
        self.calls.append(f"update_ref:{branch}:{sha}:{force}")
        return {}

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str,
    ) -> dict[str, Any]:
        self.calls.append(f"create_pr:{title}:{head}:{base}")
        return {"html_url": "https://github.test/pr/1", "number": 1}


class FakePreparer(ProfilePreparer):
    def __init__(self, preview: ContributionPreview) -> None:
        self.preview = preview

    def prepare(self, artifact_directory: Path, metadata: ContributionMetadata) -> ContributionPreview:
        return self.preview

    def prepared_contents(
        self,
        artifact_directory: Path,
        metadata: ContributionMetadata,
        preview: ContributionPreview,
    ) -> tuple[tuple[str, bytes], ...]:
        return tuple((file.path, b"content") for file in preview.files)


def test_coordinator_persists_preview_and_submits_idempotently(tmp_path: Path) -> None:
    preview = ContributionPreview(
        manufacturer_directory="signify",
        model_directory="LCT999",
        files=(ContributionPreparedFile(path="profile_library/signify/LCT999/model.json", size=20),),
    )
    metadata = ContributionMetadata(
        manufacturer="Philips",
        model_id="LCT999",
        author=ContributionAuthor(name="Test User", github="test-user"),
    )
    credential_store = CredentialStore(tmp_path / "credentials.json")
    credential_value = "secret"
    credential_store.save(StoredCredential(kind="pat", token=credential_value, github_username="octo"))
    github = FakeGitHubClient()
    coordinator = ContributionCoordinator(
        preparer=FakePreparer(preview),
        credential_store=credential_store,
        job_store=ContributionJobStore(tmp_path / "jobs"),
        github_client=github,
    )

    job = coordinator.create_job(tmp_path / "artifacts", metadata, base_sha="base-sha")
    submitted = coordinator.submit(job.id, tmp_path / "artifacts")
    submitted_again = coordinator.submit(job.id, tmp_path / "artifacts")

    assert submitted.submission is not None
    assert submitted.base_sha == "base-sha"
    assert submitted.submission.branch == f"powercalc-profile-signify-lct999-{job.id[:10]}"
    assert submitted.submission.pull_request_url == "https://github.test/pr/1"
    assert submitted_again == submitted
    assert github.calls.count("validate_user") == 1
    assert any(
        call.startswith("sync_fork_branch:octo:homeassistant-powercalc:powercalc-profile-signify-lct999-")
        for call in github.calls
    )
    assert any(call.startswith("create_commit:feat(profile): add signify LCT999") for call in github.calls)


def test_coordinator_targets_configured_repository_and_branch(tmp_path: Path) -> None:
    preview = ContributionPreview(
        manufacturer_directory="signify",
        model_directory="LCT999",
        files=(ContributionPreparedFile(path="profile_library/signify/LCT999/model.json", size=20),),
    )
    credential_store = CredentialStore(tmp_path / "credentials.json")
    credential_store.save(StoredCredential(kind="pat", token="secret", github_username="octo"))  # noqa: S106
    github = FakeGitHubClient(GitHubRepository(owner="test-owner", name="powercalc-sandbox", branch="main"))
    coordinator = ContributionCoordinator(
        preparer=FakePreparer(preview),
        credential_store=credential_store,
        job_store=ContributionJobStore(tmp_path / "jobs"),
        github_client=github,
    )
    job = coordinator.create_job(
        tmp_path / "artifacts",
        ContributionMetadata(
            manufacturer="Philips",
            model_id="LCT999",
            author=ContributionAuthor(name="Test User", github="test-user"),
        ),
        base_sha="base-sha",
    )

    submitted = coordinator.submit(job.id, tmp_path / "artifacts")

    assert submitted.submission is not None
    assert any(
        call.startswith("find_pr:octo:powercalc-profile-signify-lct999-") and call.endswith(":main")
        for call in github.calls
    )
    assert any(
        call.startswith("sync_fork_branch:octo:powercalc-sandbox:powercalc-profile-signify-lct999-")
        for call in github.calls
    )
    assert any(
        call.startswith("create_pr:Add signify LCT999 power profile:octo:") and call.endswith(":main")
        for call in github.calls
    )


def test_coordinator_uses_owned_target_without_trying_to_fork_it(tmp_path: Path) -> None:
    preview = ContributionPreview(
        manufacturer_directory="signify",
        model_directory="LCT999",
        files=(ContributionPreparedFile(path="profile_library/signify/LCT999/model.json", size=20),),
    )
    credential_store = CredentialStore(tmp_path / "credentials.json")
    credential_store.save(StoredCredential(kind="pat", token="secret", github_username="octo"))  # noqa: S106
    github = FakeGitHubClient(GitHubRepository(owner="octo", name="powercalc-sandbox", branch="main"))
    coordinator = ContributionCoordinator(
        preparer=FakePreparer(preview),
        credential_store=credential_store,
        job_store=ContributionJobStore(tmp_path / "jobs"),
        github_client=github,
    )
    job = coordinator.create_job(
        tmp_path / "artifacts",
        ContributionMetadata(
            manufacturer="Philips",
            model_id="LCT999",
            author=ContributionAuthor(name="Test User", github="octo"),
        ),
        base_sha="base-sha",
    )

    submitted = coordinator.submit(job.id, tmp_path / "artifacts")

    assert submitted.submission is not None
    assert not any(call.startswith("find_fork:") for call in github.calls)
    assert not any(call.startswith("sync_fork_branch:") for call in github.calls)
    assert any(
        call.startswith("update_ref:powercalc-profile-signify-lct999-") and call.endswith(":base-sha:True")
        for call in github.calls
    )
    assert any(
        call.startswith("create_pr:Add signify LCT999 power profile:octo:") and call.endswith(":main")
        for call in github.calls
    )


def test_coordinator_records_missing_credentials_failure(tmp_path: Path) -> None:
    preview = ContributionPreview(
        manufacturer_directory="signify",
        model_directory="LCT999",
        files=(ContributionPreparedFile(path="profile_library/signify/LCT999/model.json", size=20),),
    )
    coordinator = ContributionCoordinator(
        preparer=FakePreparer(preview),
        credential_store=CredentialStore(tmp_path / "missing.json"),
        job_store=ContributionJobStore(tmp_path / "jobs"),
    )
    job = coordinator.create_job(
        tmp_path / "artifacts",
        ContributionMetadata(
            manufacturer="Philips",
            model_id="LCT999",
            author=ContributionAuthor(name="Test User", github="test-user"),
        ),
    )

    failed = coordinator.submit(job.id, tmp_path / "artifacts")

    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "missing_credentials"


def test_coordinator_reports_missing_workflow_scope_before_writing_fork(tmp_path: Path) -> None:
    preview = ContributionPreview(
        manufacturer_directory="signify",
        model_directory="LCT999",
        files=(ContributionPreparedFile(path="profile_library/signify/LCT999/model.json", size=20),),
    )
    credential_store = CredentialStore(tmp_path / "credentials.json")
    credential_store.save(StoredCredential(kind="oauth", token="secret", github_username="octo"))  # noqa: S106
    github = FakeGitHubClient()
    github.user = GitHubUser(login="octo", scopes=("public_repo",), scopes_reported=True)
    coordinator = ContributionCoordinator(
        preparer=FakePreparer(preview),
        credential_store=credential_store,
        job_store=ContributionJobStore(tmp_path / "jobs"),
        github_client=github,
    )
    job = coordinator.create_job(
        tmp_path / "artifacts",
        ContributionMetadata(
            manufacturer="Philips",
            model_id="LCT999",
            author=ContributionAuthor(name="Test User", github="test-user"),
        ),
    )

    failed = coordinator.submit(job.id, tmp_path / "artifacts")

    assert failed.error is not None
    assert failed.error.message == (
        "GitHub authorization is missing the workflow scope; disconnect and reconnect GitHub in Settings"
    )
    assert not any(call.startswith("find_fork:") for call in github.calls)


def test_submit_preview_validation_rejects_base_or_content_drift() -> None:
    preview = ContributionPreview(
        manufacturer_directory="signify",
        model_directory="LCT999",
        files=(ContributionPreparedFile(path="profile_library/signify/LCT999/model.json", size=20, sha="one"),),
    )
    metadata = ContributionMetadata(
        manufacturer="Philips",
        model_id="LCT999",
        author=ContributionAuthor(name="Test User", github="test-user"),
    )
    job = ContributionJob(
        id="job-1",
        status="previewed",
        metadata=metadata,
        preview=preview,
        base_sha="base-one",
        created_at="2026-07-24T10:00:00Z",
        updated_at="2026-07-24T10:00:00Z",
    )

    with pytest.raises(ContributionError, match="master changed"):
        _validate_latest_preview(job, preview, "base-two")

    changed_preview = preview.model_copy(
        update={
            "files": (
                ContributionPreparedFile(
                    path="profile_library/signify/LCT999/model.json",
                    size=20,
                    sha="two",
                ),
            ),
        },
    )
    with pytest.raises(ContributionError, match="files changed"):
        _validate_latest_preview(job, changed_preview, "base-one")
