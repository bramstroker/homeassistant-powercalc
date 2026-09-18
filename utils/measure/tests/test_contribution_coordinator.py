from pathlib import Path
from typing import Any
from unittest.mock import patch

from measure.contribution.coordinator import (
    ContributionJobCoordinator,
    ContributionJobExpiredError,
    ContributionJobStore,
)
from measure.contribution.credentials import CredentialKind, CredentialStore, StoredCredential
from measure.contribution.github import GitHubClient, GitHubRepository, GitHubUser
from measure.contribution.models import ContributionAuthor, ContributionJob, ContributionJobStatus, ContributionMetadata
from measure.contribution.pull_request import deterministic_branch_name, pull_request_body
from measure.controller.light.spec import DummyLightControllerSpec
from measure.ha_app.contribution.models import (
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionAuthStatus,
    ContributionPreviewRequest,
)
from measure.ha_app.contribution.preview import metadata_from_request
from measure.ha_app.contribution.service import _validate_latest_preview
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.profile.models import PreparedProfileFile, ProfilePreview, RenderedProfileFile
from measure.profile.prepare import ProfilePreparer
from measure.request import LightMeasurementRequest
from pydantic import ValidationError
import pytest


class FakeGitHubClient(GitHubClient):
    def __init__(self, repository: GitHubRepository | None = None) -> None:
        super().__init__("token", repository=repository)
        self.calls: list[str] = []
        self.user = GitHubUser(login="octo", scopes=("public_repo", "workflow"), scopes_reported=True)

    def fetch_authenticated_user(self) -> GitHubUser:
        self.calls.append("fetch_authenticated_user")
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
        tree: list[dict[str, Any]],
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
    def __init__(self, preview: ProfilePreview) -> None:
        self.preview = preview

    def prepare(self, artifact_directory: Path, metadata: ContributionMetadata) -> ProfilePreview:
        return self.preview

    def render_contents(
        self,
        artifact_directory: Path,
        metadata: ContributionMetadata,
        preview: ProfilePreview,
    ) -> list[RenderedProfileFile]:
        return [RenderedProfileFile(path=file.path, content=b"content") for file in preview.files]


def make_preview() -> ProfilePreview:
    """The single-file signify/LCT999 preview every coordinator test builds on."""
    return ProfilePreview(
        manufacturer_directory="signify",
        model_directory="LCT999",
        files=(PreparedProfileFile(path="profile_library/signify/LCT999/model.json", size=20),),
    )


def make_metadata(github: str = "test-user") -> ContributionMetadata:
    return ContributionMetadata(
        manufacturer="Philips",
        model_id="LCT999",
        author=ContributionAuthor(name="Test User", github=github),
    )


def make_credential_store(tmp_path: Path, kind: CredentialKind = CredentialKind.PAT) -> CredentialStore:
    """A credential store already holding a token for GitHub user `octo`."""
    store = CredentialStore(tmp_path / "credentials.json")
    store.save(StoredCredential(kind=kind, token="secret", github_username="octo"))  # noqa: S106
    return store


def make_coordinator(
    tmp_path: Path,
    preview: ProfilePreview | None = None,
    credential_store: CredentialStore | None = None,
    github_client: GitHubClient | None = None,
) -> ContributionJobCoordinator:
    """A coordinator wired to fakes, storing its jobs under `tmp_path`."""
    return ContributionJobCoordinator(
        preparer=FakePreparer(preview or make_preview()),
        credential_store=credential_store or CredentialStore(tmp_path / "missing.json"),
        job_store=ContributionJobStore(tmp_path / "jobs"),
        github_client=github_client,
    )


def test_coordinator_persists_preview_and_submits_idempotently(tmp_path: Path) -> None:
    github = FakeGitHubClient()
    coordinator = make_coordinator(tmp_path, credential_store=make_credential_store(tmp_path), github_client=github)

    job = coordinator.create_job(tmp_path / "artifacts", make_metadata(), base_sha="base-sha")
    submitted = coordinator.submit(job.id, tmp_path / "artifacts")
    submitted_again = coordinator.submit(job.id, tmp_path / "artifacts")

    assert submitted.submission is not None
    assert submitted.base_sha == "base-sha"
    assert submitted.submission.branch == "powercalc-profile-signify-lct999"
    assert submitted.submission.pull_request_url == "https://github.test/pr/1"
    assert submitted_again == submitted
    assert github.calls.count("fetch_authenticated_user") == 1
    assert any(
        call.startswith("sync_fork_branch:octo:homeassistant-powercalc:powercalc-profile-signify-lct999")
        for call in github.calls
    )
    assert any(call.startswith("create_commit:feat(profile): add signify LCT999") for call in github.calls)


def test_coordinator_targets_configured_repository_and_branch(tmp_path: Path) -> None:
    github = FakeGitHubClient(GitHubRepository(owner="test-owner", name="powercalc-sandbox", branch="main"))
    coordinator = make_coordinator(tmp_path, credential_store=make_credential_store(tmp_path), github_client=github)
    job = coordinator.create_job(tmp_path / "artifacts", make_metadata(), base_sha="base-sha")

    submitted = coordinator.submit(job.id, tmp_path / "artifacts")

    assert submitted.submission is not None
    assert any(
        call.startswith("find_pr:octo:powercalc-profile-signify-lct999") and call.endswith(":main")
        for call in github.calls
    )
    assert any(
        call.startswith("sync_fork_branch:octo:powercalc-sandbox:powercalc-profile-signify-lct999")
        for call in github.calls
    )
    assert any(
        call.startswith("create_pr:Add signify LCT999 power profile:octo:") and call.endswith(":main")
        for call in github.calls
    )


def test_coordinator_uses_owned_target_without_trying_to_fork_it(tmp_path: Path) -> None:
    github = FakeGitHubClient(GitHubRepository(owner="octo", name="powercalc-sandbox", branch="main"))
    coordinator = make_coordinator(tmp_path, credential_store=make_credential_store(tmp_path), github_client=github)
    job = coordinator.create_job(tmp_path / "artifacts", make_metadata("octo"), base_sha="base-sha")

    submitted = coordinator.submit(job.id, tmp_path / "artifacts")

    assert submitted.submission is not None
    assert not any(call.startswith("find_fork:") for call in github.calls)
    assert not any(call.startswith("sync_fork_branch:") for call in github.calls)
    assert any(
        call.startswith("update_ref:powercalc-profile-signify-lct999") and call.endswith(":base-sha:True")
        for call in github.calls
    )
    assert any(
        call.startswith("create_pr:Add signify LCT999 power profile:octo:") and call.endswith(":main")
        for call in github.calls
    )


def test_coordinator_records_missing_credentials_failure(tmp_path: Path) -> None:
    coordinator = make_coordinator(tmp_path)
    job = coordinator.create_job(tmp_path / "artifacts", make_metadata())

    failed = coordinator.submit(job.id, tmp_path / "artifacts")

    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "missing_credentials"


@pytest.mark.parametrize(
    "upstream_sha,expected_error",
    [(None, "Upstream branch was not found"), ("new-sha", "changed after preview")],
)
def test_coordinator_rejects_missing_or_changed_upstream_before_writing(
    tmp_path: Path, upstream_sha: str | None, expected_error: str
) -> None:
    github = FakeGitHubClient()
    coordinator = make_coordinator(tmp_path, credential_store=make_credential_store(tmp_path), github_client=github)
    job = coordinator.create_job(tmp_path / "artifacts", make_metadata(), base_sha="base-sha")
    response = {"object": {"sha": upstream_sha}} if upstream_sha is not None else None

    with patch.object(github, "get_ref", return_value=response) as get_ref:
        failed = coordinator.submit(job.id, tmp_path / "artifacts")

    assert failed.status is ContributionJobStatus.FAILED
    assert failed.submission is None
    assert failed.error is not None
    assert expected_error in failed.error.message
    assert coordinator.job_store.load(job.id) == failed
    get_ref.assert_called_once_with(github.repository.owner, github.repository.name, github.repository.branch)
    assert github.calls == ["fetch_authenticated_user", "find_fork:octo:homeassistant-powercalc"]


def test_coordinator_rejects_missing_fork_base_before_writing(tmp_path: Path) -> None:
    github = FakeGitHubClient()
    coordinator = make_coordinator(tmp_path, credential_store=make_credential_store(tmp_path), github_client=github)
    job = coordinator.create_job(tmp_path / "artifacts", make_metadata(), base_sha="base-sha")

    with patch.object(github, "get_ref", side_effect=[{"object": {"sha": "base-sha"}}, None, None]) as get_ref:
        failed = coordinator.submit(job.id, tmp_path / "artifacts")

    assert failed.status is ContributionJobStatus.FAILED
    assert failed.error is not None
    assert failed.error.message == "The fork base branch was not found"
    assert coordinator.job_store.load(job.id) == failed
    assert get_ref.call_args.args == ("octo", github.repository.name, github.repository.branch)
    assert github.calls == ["fetch_authenticated_user", "find_fork:octo:homeassistant-powercalc"]


@pytest.mark.parametrize("owns_repository", [False, True])
def test_coordinator_creates_missing_contribution_branch(tmp_path: Path, owns_repository: bool) -> None:
    repository = GitHubRepository(owner="octo" if owns_repository else "upstream", name="profiles", branch="main")
    github = FakeGitHubClient(repository)
    coordinator = make_coordinator(tmp_path, credential_store=make_credential_store(tmp_path), github_client=github)
    job = coordinator.create_job(tmp_path / "artifacts", make_metadata(), base_sha="base-sha")
    references = [{"object": {"sha": "base-sha"}}, None]
    if not owns_repository:
        references.append({"object": {"sha": "old-fork-sha"}})

    with patch.object(github, "get_ref", side_effect=references):
        submitted = coordinator.submit(job.id, tmp_path / "artifacts")

    assert submitted.status is ContributionJobStatus.SUBMITTED
    branch = deterministic_branch_name(job.preview)
    initial_sha = "base-sha" if owns_repository else "old-fork-sha"
    create_call = f"create_ref:{branch}:{initial_sha}"
    assert create_call in github.calls
    if not owns_repository:
        sync_call = f"sync_fork_branch:octo:profiles:{branch}"
        assert (
            github.calls.index(create_call) < github.calls.index(sync_call) < github.calls.index("get_commit:base-sha")
        )
    assert f"update_ref:{branch}:commit-sha:True" in github.calls


def test_coordinator_reports_missing_workflow_scope_before_writing_fork(tmp_path: Path) -> None:
    github = FakeGitHubClient()
    github.user = GitHubUser(login="octo", scopes=("public_repo",), scopes_reported=True)
    coordinator = make_coordinator(
        tmp_path,
        credential_store=make_credential_store(tmp_path, kind=CredentialKind.OAUTH),
        github_client=github,
    )
    job = coordinator.create_job(tmp_path / "artifacts", make_metadata())

    failed = coordinator.submit(job.id, tmp_path / "artifacts")

    assert failed.error is not None
    assert failed.error.message == (
        "GitHub authorization is missing the workflow scope; disconnect and reconnect GitHub in Settings"
    )
    assert not any(call.startswith("find_fork:") for call in github.calls)


def test_coordinator_accepts_classic_repo_scope_as_public_repo(tmp_path: Path) -> None:
    github = FakeGitHubClient()
    github.user = GitHubUser(login="octo", scopes=("repo", "workflow"), scopes_reported=True)
    coordinator = make_coordinator(tmp_path, credential_store=make_credential_store(tmp_path), github_client=github)
    job = coordinator.create_job(tmp_path / "artifacts", make_metadata(), base_sha="base-sha")

    submitted = coordinator.submit(job.id, tmp_path / "artifacts")

    assert submitted.error is None
    assert submitted.submission is not None


def test_coordinator_refreshes_existing_pull_request_with_new_commit(tmp_path: Path) -> None:
    class ExistingPullRequestClient(FakeGitHubClient):
        def find_pull_request(self, owner: str, repo: str, *, head: str, base: str) -> dict[str, Any] | None:
            self.calls.append(f"find_pr:{head}:{base}")
            return {"html_url": "https://github.test/pr/7", "number": 7, "head": {"sha": "old-commit"}}

    github = ExistingPullRequestClient()
    coordinator = make_coordinator(tmp_path, credential_store=make_credential_store(tmp_path), github_client=github)
    job = coordinator.create_job(tmp_path / "artifacts", make_metadata(), base_sha="base-sha")

    submitted = coordinator.submit(job.id, tmp_path / "artifacts")

    assert submitted.submission is not None
    assert submitted.submission.pull_request_url == "https://github.test/pr/7"
    assert submitted.submission.pull_request_number == 7
    # The branch is force-updated with the freshly prepared files even though the
    # pull request already exists, so a re-measured profile replaces stale data.
    assert submitted.submission.commit_sha == "commit-sha"
    assert any(call.startswith("update_ref:powercalc-profile-signify-lct999:commit-sha:True") for call in github.calls)
    assert not any(call.startswith("create_pr:") for call in github.calls)


def test_coordinator_submit_of_unknown_job_reports_expired_preview(tmp_path: Path) -> None:
    coordinator = make_coordinator(tmp_path)

    with pytest.raises(ContributionJobExpiredError, match="refresh the preview"):
        coordinator.submit("0badc0ffee", tmp_path / "artifacts")


def test_deterministic_branch_name_collapses_non_alphanumeric_runs() -> None:
    preview = ProfilePreview(manufacturer_directory="ajax online", model_directory="AJ-100 (EU)+", files=())

    assert deterministic_branch_name(preview) == "powercalc-profile-ajax-online-aj-100-eu"


def test_pull_request_body_reports_the_integration_of_the_measured_entity() -> None:
    metadata = ContributionMetadata(
        manufacturer="Philips",
        model_id="LCT999",
        measure_type="light",
        integration="hue",
        author=ContributionAuthor(name="Test User", github="test-user"),
    )
    job = ContributionJob(
        id="job-1",
        status=ContributionJobStatus.PREVIEWED,
        metadata=metadata,
        preview=ProfilePreview(manufacturer_directory="signify", model_directory="LCT999", files=()),
        created_at="2026-07-16T12:00:00Z",
        updated_at="2026-07-16T12:00:00Z",
    )

    without_integration = job.model_copy(
        update={"metadata": metadata.model_copy(update={"integration": None})},
    )

    body = pull_request_body(job)

    assert "## Home Assistant Device information\n\n- Measure type: light\n- Integration: hue\n" in body
    assert "- Integration:" not in pull_request_body(without_integration)


def test_contribution_author_rejects_blank_required_fields() -> None:
    with pytest.raises(ValueError, match="value is required"):
        ContributionAuthor(name="   ", github="octo")
    with pytest.raises(ValueError, match="value is required"):
        ContributionAuthor(name="Test User", github=" ")
    author = ContributionAuthor(name=" Test User ", github="octo", email="   ")
    assert author.name == "Test User"
    assert author.email is None


@pytest.mark.parametrize("email", ["invalid", "a@", "a@b", "a@@example.com", "a b@example.com"])
def test_contribution_author_rejects_invalid_email(email: str) -> None:
    with pytest.raises(ValueError, match="valid email address"):
        ContributionAuthor(name="Tester", github="tester", email=email)


@pytest.mark.parametrize("email", ["name@example.com", "name+test@sub.example.com"])
def test_contribution_author_accepts_valid_email(email: str) -> None:
    assert ContributionAuthor(name="Tester", github="tester", email=f" {email} ").email == email


def test_metadata_from_request_maps_validation_errors_to_invalid_metadata() -> None:
    request = LightMeasurementRequest(
        model_id="LCT010",
        product_name="Test light",
        measure_device="Test meter",
        power_meter=DummyPowerMeterSpec(),
        controller=DummyLightControllerSpec(),
    )
    auth = ContributionAuthStatus(authenticated=True, connected=True, username="octo")
    payload = ContributionPreviewRequest(
        manufacturer_name="Signify",
        model_id="LCT010",
        product_name="Test light",
        contributor="Test User",
        gtins=["invalid"],
    )

    with pytest.raises(ContributionApiError, match="invalid GTIN") as info:
        metadata_from_request(request, payload, auth)
    assert info.value.code == ContributionApiErrorCode.INVALID_METADATA
    assert info.value.field == "gtins"

    for payload_field in ("contributor", "contributor_github", "manufacturer_name"):
        invalid = payload.model_copy(update={"gtins": [], payload_field: " "})
        with pytest.raises(ContributionApiError) as info:
            metadata_from_request(request, invalid, auth)
        assert info.value.field == payload_field

    metadata = metadata_from_request(request, payload.model_copy(update={"gtins": []}), auth, "hue")
    assert metadata.measure_type == "light"
    assert metadata.measure_device == "Test meter"
    assert metadata.integration == "hue"


@pytest.mark.parametrize("mains_voltage", [90, 110, 240, 260])
def test_contribution_preview_request_rejects_unsupported_mains_voltage(mains_voltage: int) -> None:
    with pytest.raises(ValidationError):
        ContributionPreviewRequest(
            manufacturer_name="Signify",
            model_id="LCT010",
            product_name="Hue lamp",
            contributor="Test User",
            mains_voltage=mains_voltage,  # type: ignore[arg-type]
        )


def test_submit_preview_validation_rejects_base_or_content_drift() -> None:
    preview = ProfilePreview(
        manufacturer_directory="signify",
        model_directory="LCT999",
        files=(PreparedProfileFile(path="profile_library/signify/LCT999/model.json", size=20, sha="one"),),
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

    with pytest.raises(ContributionApiError, match="master changed"):
        _validate_latest_preview(job, preview, "base-two")

    changed_preview = preview.model_copy(
        update={
            "files": (
                PreparedProfileFile(
                    path="profile_library/signify/LCT999/model.json",
                    size=20,
                    sha="two",
                ),
            ),
        },
    )
    with pytest.raises(ContributionApiError, match="files changed"):
        _validate_latest_preview(job, changed_preview, "base-one")
