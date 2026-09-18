from dataclasses import dataclass
from functools import partial
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from measure.contribution.coordinator import (
    ContributionJobCoordinator,
    ContributionJobExpiredError,
    ContributionJobStore,
)
from measure.contribution.credentials import CredentialStore, StoredCredential
from measure.contribution.github import GitHubApiError
from measure.ha_app.contribution.models import (
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
)
from measure.ha_app.contribution.service import SharedContributionService
from measure.profile.models import RenderedProfileFile
from measure.request import MeasurementRequest, parse_measurement_request
import pytest

from tests.test_contribution_coordinator import FakeGitHubClient


@dataclass
class ContributionSession:
    service: SharedContributionService
    artifacts: Path
    request: MeasurementRequest
    payload: ContributionPreviewRequest
    github: FakeGitHubClient

    def preview(self) -> ContributionPreviewResponse:
        return self.service.build_preview(
            session_id="session",
            request=self.request,
            artifact_root=self.artifacts,
            payload=self.payload,
        )


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ContributionSession:
    github = FakeGitHubClient()
    monkeypatch.setattr(github, "get_file", MagicMock(return_value=b"{}"))
    monkeypatch.setattr("measure.ha_app.contribution.service.GitHubClient", lambda _token: github)
    CredentialStore(tmp_path / "contribution/credentials.json").save(
        StoredCredential(kind="pat", token="test-token", github_username="octo"),  # noqa: S106
    )
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "model.json").write_text(
        json.dumps(
            {
                "name": "Test device",
                "calculation_strategy": "fixed",
                "fixed_config": {"power": 5},
                "mains_voltage": 230,
            }
        )
    )
    return ContributionSession(
        service=SharedContributionService(tmp_path),
        artifacts=artifacts,
        github=github,
        request=parse_measurement_request(
            {"measure_type": "recorder", "model_id": "test-model", "power_meter": {"type": "dummy"}}
        ),
        payload=ContributionPreviewRequest(
            manufacturer_name="Acme",
            model_id="test-model",
            product_name="Test device",
            contributor="Octo",
            contributor_github="octo",
            notes="Measured locally",
        ),
    )


def test_preview_archive_and_submission_share_pinned_profile(session: ContributionSession) -> None:
    preview = session.preview()
    assert preview.job_id is not None
    assert preview.base_sha == "base-sha"
    assert preview.fork_repository == f"octo/{session.github.repository.name}"
    assert preview.notes == "Measured locally"
    assert preview.model_json is not None
    assert preview.model_json["authors"] == [{"name": "Octo", "github": "octo"}]
    with ZipFile(BytesIO(session.service.prepared_archive(preview.job_id))) as archive:
        model_path = next(name for name in archive.namelist() if name.endswith("model.json"))
        assert json.loads(archive.read(model_path)) == preview.model_json
    submitted = session.service.submit(preview=preview, artifact_root=session.artifacts)
    assert submitted.pull_request_url == "https://github.test/pr/1"
    assert submitted.branch_name == preview.branch_name


def test_refresh_reuses_reference_and_expires_previous_archive(session: ContributionSession, tmp_path: Path) -> None:
    old_reference = tmp_path / "contribution/reference/old-sha"
    old_reference.mkdir(parents=True)
    first = session.preview()
    second = session.preview()
    assert not old_reference.exists()
    assert first.job_id is not None
    assert second.job_id is not None
    assert session.github.get_file.call_count == 2
    with pytest.raises(ContributionApiError, match="preview expired"):
        session.service.prepared_archive(first.job_id)
    assert session.service.prepared_archive(second.job_id)
    assert not (tmp_path / f"contribution/prepared/{first.job_id}.zip").exists()


def test_missing_prepared_archive_requests_refresh(session: ContributionSession, tmp_path: Path) -> None:
    preview = session.preview()
    assert preview.job_id is not None
    (tmp_path / f"contribution/prepared/{preview.job_id}.zip").unlink()
    with pytest.raises(ContributionApiError, match="Prepared profile expired"):
        session.service.prepared_archive(preview.job_id)


@pytest.mark.parametrize("field", ["name", "model"])
def test_preview_preparation_errors_preserve_api_codes(session: ContributionSession, field: str) -> None:
    if field == "name":
        session.payload = session.payload.model_copy(update={"product_name": ""})
        expected = ContributionApiErrorCode.INVALID_METADATA
    else:
        (session.artifacts / "model.json").unlink()
        expected = ContributionApiErrorCode.ARTIFACTS_REQUIRED
    with pytest.raises(ContributionApiError) as error:
        session.preview()
    assert error.value.code is expected


@pytest.mark.parametrize("authenticated", [False, True])
def test_github_errors_are_translated(session: ContributionSession, authenticated: bool) -> None:
    preview = session.preview()
    call = (
        partial(session.service.submit, preview=preview, artifact_root=session.artifacts)
        if authenticated
        else session.preview
    )
    with (
        patch.object(session.github, "get_ref", side_effect=GitHubApiError("GitHub unavailable")),
        pytest.raises(ContributionApiError, match="GitHub unavailable") as error,
    ):
        call()
    assert error.value.code is ContributionApiErrorCode.SUBMISSION_FAILED


def test_missing_upstream_branch_is_reported(session: ContributionSession) -> None:
    with (
        patch.object(session.github, "get_ref", return_value=None),
        pytest.raises(ContributionApiError, match="was not found"),
    ):
        session.preview()


@pytest.mark.parametrize("missing", ["job_id", "job", "credentials", "artifacts"])
def test_submission_prerequisites(session: ContributionSession, tmp_path: Path, missing: str) -> None:
    preview = session.preview()
    expected = ContributionApiErrorCode.PREVIEW_REQUIRED
    if missing == "job_id":
        preview = preview.model_copy(update={"job_id": None})
    elif missing == "job":
        (tmp_path / f"contribution/jobs/{preview.job_id}.json").unlink()
    elif missing == "credentials":
        session.service.disconnect()
        expected = ContributionApiErrorCode.AUTH_UNAVAILABLE
    else:
        (session.artifacts / "model.json").unlink()
        expected = ContributionApiErrorCode.ARTIFACTS_REQUIRED
    with pytest.raises(ContributionApiError) as error:
        session.service.submit(preview=preview, artifact_root=session.artifacts)
    assert error.value.code is expected


def test_submission_reports_job_failure(session: ContributionSession) -> None:
    preview = session.preview()
    with (
        patch.object(session.github, "fetch_authenticated_user", side_effect=GitHubApiError("No access")),
        pytest.raises(ContributionApiError, match="No access") as error,
    ):
        session.service.submit(preview=preview, artifact_root=session.artifacts)
    assert error.value.code is ContributionApiErrorCode.SUBMISSION_FAILED


@pytest.mark.parametrize("expired", [True, False])
def test_submission_requires_a_completed_job(session: ContributionSession, tmp_path: Path, expired: bool) -> None:
    preview = session.preview()
    assert preview.job_id is not None
    job = ContributionJobStore(tmp_path / "contribution/jobs").load(preview.job_id)
    with (
        patch.object(
            ContributionJobCoordinator,
            "submit",
            side_effect=ContributionJobExpiredError("Preview expired") if expired else None,
            return_value=job,
        ),
        pytest.raises(ContributionApiError) as error,
    ):
        session.service.submit(preview=preview, artifact_root=session.artifacts)
    expected = ContributionApiErrorCode.PREVIEW_REQUIRED if expired else ContributionApiErrorCode.SUBMISSION_FAILED
    assert error.value.code is expected


def test_failed_archive_replacement_cleans_up_temporary_file(session: ContributionSession, tmp_path: Path) -> None:
    with (
        patch.object(Path, "replace", side_effect=OSError("No space")),
        pytest.raises(OSError, match="No space"),
    ):
        session.service._save_prepared_archive("job", [RenderedProfileFile("model.json", b"{}")])  # noqa: SLF001
    assert list((tmp_path / "contribution/prepared").iterdir()) == []
