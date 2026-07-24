from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from measure.contribution.github import GitHubApiError, GitHubClient, GitHubRepository
import pytest


@dataclass
class Response:
    status_code: int
    payload: object
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> object:
        return self.payload


class FakeTransport:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: object) -> Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def test_github_client_starts_and_polls_oauth_device_flow_without_auth_header() -> None:
    expected_value = "token"
    transport = FakeTransport(
        [
            Response(200, {"device_code": "device", "user_code": "ABCD"}),
            Response(200, {"access_token": expected_value}),
        ],
    )
    client = GitHubClient(transport=transport)

    assert client.start_device_flow("client-id", ("repo",))["device_code"] == "device"
    assert client.poll_device_flow("client-id", "device")["access_token"] == expected_value

    assert all("Authorization" not in call["headers"] for call in transport.calls)
    assert transport.calls[0]["url"] == "https://github.com/login/device/code"
    assert transport.calls[1]["url"] == "https://github.com/login/oauth/access_token"


def test_github_client_validates_user_and_discovers_fork() -> None:
    transport = FakeTransport(
        [
            Response(
                200,
                {"login": "octo", "name": "Octo", "email": None},
                {"X-OAuth-Scopes": "read:user, public_repo"},
            ),
            Response(
                200,
                {
                    "fork": True,
                    "name": "homeassistant-powercalc",
                    "owner": {"login": "octo"},
                    "parent": {"full_name": "bramstroker/homeassistant-powercalc"},
                },
            ),
        ],
    )
    client = GitHubClient("token", transport=transport)

    user = client.validate_user()
    assert user.login == "octo"
    assert user.scopes == ("read:user", "public_repo")
    assert user.scopes_reported is True
    assert client.find_fork("octo") is not None
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer token"


def test_github_client_rejects_same_name_repository_that_is_not_upstream_fork() -> None:
    transport = FakeTransport(
        [
            Response(
                200,
                {
                    "fork": True,
                    "name": "homeassistant-powercalc",
                    "owner": {"login": "octo"},
                    "parent": {"full_name": "someone/else"},
                },
            ),
        ],
    )

    assert GitHubClient("token", transport=transport).find_fork("octo") is None


def test_github_repository_loads_repository_and_branch_from_environment() -> None:
    repository = GitHubRepository.from_environment(
        {
            "POWERCALC_GITHUB_REPOSITORY": "test-owner/powercalc-sandbox",
            "POWERCALC_GITHUB_BRANCH": "main",
        },
    )

    assert repository.full_name == "test-owner/powercalc-sandbox"
    assert repository.branch == "main"


@pytest.mark.parametrize(
    "environment",
    [
        {"POWERCALC_GITHUB_REPOSITORY": "missing-repository"},
        {"POWERCALC_GITHUB_REPOSITORY": "owner/repo/extra"},
        {"POWERCALC_GITHUB_BRANCH": "../unsafe"},
    ],
)
def test_github_repository_rejects_invalid_environment(environment: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        GitHubRepository.from_environment(environment)


def test_github_client_forks_configured_repository_and_waits_for_configured_branch() -> None:
    transport = FakeTransport(
        [
            Response(202, {}),
            Response(200, {"login": "octo"}),
            Response(
                200,
                {
                    "fork": True,
                    "name": "powercalc-sandbox",
                    "owner": {"login": "octo"},
                    "parent": {"full_name": "test-owner/powercalc-sandbox"},
                },
            ),
            Response(200, {"object": {"sha": "base-sha"}}),
        ],
    )
    repository = GitHubRepository(owner="test-owner", name="powercalc-sandbox", branch="main")
    client = GitHubClient("token", transport=transport, repository=repository)

    fork = client.create_fork(poll_attempts=1, poll_interval=0)

    assert fork["name"] == "powercalc-sandbox"
    assert transport.calls[0]["url"] == "https://api.github.com/repos/test-owner/powercalc-sandbox/forks"
    assert transport.calls[2]["url"] == "https://api.github.com/repos/octo/powercalc-sandbox"
    assert transport.calls[3]["url"].endswith("/git/ref/heads/main")


def test_github_client_reads_sha_pinned_file_and_creates_ready_pull_request() -> None:
    encoded = base64.b64encode(b'{"ok": true}').decode()
    transport = FakeTransport(
        [
            Response(200, {"encoding": "base64", "content": encoded}),
            Response(201, {"html_url": "https://github.test/pull/1", "number": 1}),
        ],
    )
    client = GitHubClient("token", transport=transport)

    assert client.get_file("owner", "repo", "profile_library/library.json", "base-sha") == b'{"ok": true}'
    client.create_pull_request("owner", "repo", title="Title", head="octo:branch", base="master", body="Body")

    assert transport.calls[0]["params"] == {"ref": "base-sha"}
    assert transport.calls[1]["json"]["draft"] is False
    assert transport.calls[1]["json"]["maintainer_can_modify"] is True


def test_github_client_fetches_upstream_through_contribution_branch() -> None:
    transport = FakeTransport([Response(200, {"message": "Successfully fetched and fast-forwarded"})])
    client = GitHubClient("token", transport=transport)

    client.sync_fork_branch("octo", "homeassistant-powercalc", "powercalc-profile-test")

    assert transport.calls[0]["url"].endswith("/repos/octo/homeassistant-powercalc/merge-upstream")
    assert transport.calls[0]["json"] == {"branch": "powercalc-profile-test"}


def test_github_client_tolerates_merge_conflict_while_fetching_upstream_objects() -> None:
    client = GitHubClient(
        "token",
        transport=FakeTransport([Response(409, {"message": "There are merge conflicts"})]),
    )

    client.sync_fork_branch("octo", "homeassistant-powercalc", "powercalc-profile-test")


def test_github_client_raises_api_message() -> None:
    client = GitHubClient("token", transport=FakeTransport([Response(403, {"message": "rate limited"})]))

    with pytest.raises(GitHubApiError, match="rate limited"):
        client.validate_user()


def test_github_client_falls_back_to_blob_api_for_large_files() -> None:
    encoded = base64.b64encode(b'{"large": true}').decode()
    transport = FakeTransport(
        [
            Response(200, {"encoding": "none", "content": "", "sha": "blob-sha"}),
            Response(200, {"encoding": "base64", "content": encoded}),
        ],
    )
    client = GitHubClient("token", transport=transport)

    assert client.get_file("owner", "repo", "profile_library/library.json", "base-sha") == b'{"large": true}'
    assert transport.calls[1]["url"] == "https://api.github.com/repos/owner/repo/git/blobs/blob-sha"


def test_github_client_reports_missing_blob_content() -> None:
    transport = FakeTransport([Response(200, {"encoding": "none", "content": ""})])
    client = GitHubClient("token", transport=transport)

    with pytest.raises(GitHubApiError, match="did not return content or a blob sha"):
        client.get_file("owner", "repo", "profile_library/library.json", "base-sha")
