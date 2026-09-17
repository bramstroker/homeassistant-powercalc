from functools import partial
from pathlib import Path
from unittest.mock import MagicMock, patch

from measure.contribution.github import REQUIRED_OAUTH_SCOPES, GitHubApiError, GitHubClient, GitHubUser
from measure.ha_app.contribution.models import ContributionApiError, ContributionApiErrorCode, ContributionAuthMethod
from measure.ha_app.contribution.service import SharedContributionService
from pydantic import SecretStr
import pytest


def test_pat_connection_persists_and_disconnect_clears_credentials(tmp_path: Path) -> None:
    github = MagicMock(spec=GitHubClient)
    github.fetch_authenticated_user.return_value = GitHubUser(
        login="octo",
        scopes=("public_repo", "workflow"),
        scopes_reported=True,
    )
    service = SharedContributionService(tmp_path)
    assert not service.auth_status().authenticated

    with patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github):
        status = service.connect_pat(SecretStr("test-token"))

    assert status.method is ContributionAuthMethod.PAT
    assert status.username == "octo"
    assert status.permissions_verified
    assert SharedContributionService(tmp_path).auth_status() == status
    assert not service.disconnect().authenticated
    assert not SharedContributionService(tmp_path).auth_status().connected


@pytest.mark.parametrize("complete_uri", [None, "https://github.com/login/device?user_code=123"])
def test_device_flow_start(tmp_path: Path, complete_uri: str | None) -> None:
    github = MagicMock(spec=GitHubClient)
    github.start_device_flow.return_value = {
        "device_code": "device",
        "user_code": "123",
        "verification_uri": "https://github.com/login/device",
        "verification_uri_complete": complete_uri,
        "expires_in": 900,
        "interval": 5,
    }
    with patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github):
        result = SharedContributionService(tmp_path).start_device_flow("client")
    github.start_device_flow.assert_called_once_with("client", REQUIRED_OAUTH_SCOPES)
    assert result.device_code == "device"
    assert result.verification_uri_complete == complete_uri
    assert result.interval == 5


@pytest.mark.parametrize("operation", ["pat", "start", "poll", "identity"])
def test_auth_errors_are_translated_without_saving_credentials(tmp_path: Path, operation: str) -> None:
    github = MagicMock(spec=GitHubClient)
    github.poll_device_flow.return_value = {"access_token": "test-token"}
    failing_method = {
        "pat": github.fetch_authenticated_user,
        "start": github.start_device_flow,
        "poll": github.poll_device_flow,
        "identity": github.fetch_authenticated_user,
    }[operation]
    failing_method.side_effect = GitHubApiError("GitHub unavailable")
    service = SharedContributionService(tmp_path)
    call = {
        "pat": partial(service.connect_pat, SecretStr("test-token")),
        "start": partial(service.start_device_flow, "client"),
        "poll": partial(service.poll_device_flow, "client", "device"),
        "identity": partial(service.poll_device_flow, "client", "device"),
    }[operation]
    with (
        patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github),
        pytest.raises(ContributionApiError, match="GitHub unavailable") as error,
    ):
        call()
    assert error.value.code is ContributionApiErrorCode.AUTH_UNAVAILABLE
    assert not service.auth_status().authenticated


@pytest.mark.parametrize("oauth_error,status", [("expired_token", "expired"), ("access_denied", "denied")])
def test_device_flow_terminal_states(tmp_path: Path, oauth_error: str, status: str) -> None:
    github = MagicMock(spec=GitHubClient)
    github.poll_device_flow.return_value = {"error": oauth_error}
    with patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github):
        result = SharedContributionService(tmp_path).poll_device_flow("client", "device")
    assert result.status == status
    assert result.message == oauth_error
    github.fetch_authenticated_user.assert_not_called()


@pytest.mark.parametrize("token", [None, "", 42])
def test_device_flow_requires_nonempty_token(tmp_path: Path, token: object) -> None:
    github = MagicMock(spec=GitHubClient)
    github.poll_device_flow.return_value = {"access_token": token}
    with (
        patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github),
        pytest.raises(ContributionApiError, match="did not return an access token"),
    ):
        SharedContributionService(tmp_path).poll_device_flow("client", "device")


def test_device_flow_uses_response_scopes_when_identity_does_not_report_them(tmp_path: Path) -> None:
    github = MagicMock(spec=GitHubClient)
    github.poll_device_flow.return_value = {"access_token": "test-token", "scope": "public_repo workflow"}
    github.fetch_authenticated_user.return_value = GitHubUser(login="octo", scopes=(), scopes_reported=False)
    with patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github):
        result = SharedContributionService(tmp_path).poll_device_flow("client", "device")
    assert result.auth is not None
    assert result.auth.method is ContributionAuthMethod.OAUTH_DEVICE
    assert result.auth.permissions_verified


@pytest.mark.parametrize("interval", [True, False, "0", "-1", None])
def test_invalid_retry_intervals_are_ignored(tmp_path: Path, interval: object) -> None:
    github = MagicMock(spec=GitHubClient)
    github.poll_device_flow.return_value = {"error": "slow_down", "interval": interval}
    with patch("measure.ha_app.contribution.auth.GitHubClient", return_value=github):
        result = SharedContributionService(tmp_path).poll_device_flow("client", "device")
    assert result.retry_after is None
