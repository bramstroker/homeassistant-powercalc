import base64
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import call, patch

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


def test_github_writes_commit_tree_and_branch_references() -> None:
    parent = {"sha": "parent-sha", "tree": {"sha": "base-tree-sha"}}
    reference = {"ref": "refs/heads/profile", "object": {"sha": "commit-sha"}}
    transport = FakeTransport(
        [
            Response(200, parent),
            Response(201, {"sha": "blob-sha"}),
            Response(201, {"sha": "tree-sha"}),
            Response(201, {"sha": "commit-sha"}),
            Response(201, reference),
            Response(200, reference),
        ]
    )
    client = GitHubClient("test-token", transport=transport)
    tree = [{"path": "profile_library/acme/lamp/model.json", "mode": "100644", "type": "blob", "sha": "blob-sha"}]

    assert client.get_commit("octo", "repo", "parent-sha") == parent
    assert client.create_blob("octo", "repo", "e30=") == "blob-sha"
    assert client.create_tree("octo", "repo", "base-tree-sha", tree) == "tree-sha"
    assert client.create_commit("octo", "repo", "Add lamp profile", "tree-sha", "parent-sha") == "commit-sha"
    assert client.create_ref("octo", "repo", "profile", "commit-sha") == reference
    assert client.update_ref("octo", "repo", "profile", "commit-sha") == reference

    base_url = "https://api.github.com/repos/octo/repo/git"
    assert [request["url"] for request in transport.calls] == [
        f"{base_url}/commits/parent-sha",
        f"{base_url}/blobs",
        f"{base_url}/trees",
        f"{base_url}/commits",
        f"{base_url}/refs",
        f"{base_url}/refs/heads/profile",
    ]
    assert [request["method"] for request in transport.calls] == ["GET", "POST", "POST", "POST", "POST", "PATCH"]
    assert [request["json"] for request in transport.calls] == [
        None,
        {"content": "e30=", "encoding": "base64"},
        {"base_tree": "base-tree-sha", "tree": tree},
        {"message": "Add lamp profile", "tree": "tree-sha", "parents": ["parent-sha"]},
        {"ref": "refs/heads/profile", "sha": "commit-sha"},
        {"sha": "commit-sha", "force": False},
    ]
    assert all(request["headers"]["Authorization"] == "Bearer test-token" for request in transport.calls)
    assert all(request["timeout"] == 30 for request in transport.calls)


def test_github_honors_explicit_encoding_and_force_update() -> None:
    transport = FakeTransport([Response(201, {"sha": "blob-sha"}), Response(200, {})])
    client = GitHubClient("test-token", transport=transport)

    assert client.create_blob("octo", "repo", "{}", encoding="utf-8") == "blob-sha"
    client.update_ref("octo", "repo", "profile", "commit-sha", force=True)

    assert transport.calls[0]["json"] == {"content": "{}", "encoding": "utf-8"}
    assert transport.calls[1]["json"] == {"sha": "commit-sha", "force": True}


def test_fork_polling_waits_until_default_branch_is_available() -> None:
    fork = {
        "fork": True,
        "name": "homeassistant-powercalc",
        "owner": {"login": "octo"},
        "parent": {"full_name": "bramstroker/homeassistant-powercalc"},
    }
    transport = FakeTransport(
        [
            Response(202, {}),
            Response(200, {"login": "octo"}),
            Response(404, {}),
            Response(200, fork),
            Response(404, {}),
            Response(200, fork),
            Response(200, {"object": {"sha": "ready"}}),
        ]
    )
    client = GitHubClient("token", transport=transport)

    with patch("measure.contribution.github.time.sleep") as sleep:
        assert client.create_fork(poll_attempts=3, poll_interval=2) == fork

    assert sleep.call_args_list == [call(2), call(2)]
    assert transport.responses == []


def test_fork_polling_times_out_without_creating_another_fork() -> None:
    transport = FakeTransport(
        [
            Response(202, {}),
            Response(200, {"login": "octo"}),
            Response(404, {}),
            Response(404, {}),
        ]
    )
    client = GitHubClient("token", transport=transport)

    with patch("measure.contribution.github.time.sleep") as sleep, pytest.raises(GitHubApiError, match="after polling"):
        client.create_fork(poll_attempts=2, poll_interval=1)

    assert sleep.call_count == 2
    assert [request["method"] for request in transport.calls] == ["POST", "GET", "GET", "GET"]


def test_authenticated_request_requires_token_before_sending() -> None:
    transport = FakeTransport([])

    with pytest.raises(GitHubApiError, match="token is required"):
        GitHubClient(transport=transport).fetch_authenticated_user()

    assert transport.calls == []


def test_github_rejects_invalid_json_with_response_status() -> None:
    response = Response(502, None)
    error = ValueError("Invalid JSON")
    client = GitHubClient("token", transport=FakeTransport([response]))

    with (
        patch.object(response, "json", side_effect=error),
        pytest.raises(GitHubApiError, match="invalid JSON with status 502") as raised,
    ):
        client.fetch_authenticated_user()

    assert raised.value.__cause__ is error


@pytest.mark.parametrize("payload", [[], None, "unexpected"])
def test_github_rejects_non_object_user_response(payload: object) -> None:
    client = GitHubClient("token", transport=FakeTransport([Response(200, payload)]))

    with pytest.raises(GitHubApiError, match="must be an object"):
        client.fetch_authenticated_user()


@pytest.mark.parametrize("payload", [{}, None, "unexpected"])
def test_github_rejects_non_list_pull_request_response(payload: object) -> None:
    client = GitHubClient("token", transport=FakeTransport([Response(200, payload)]))

    with pytest.raises(GitHubApiError, match="must be a list"):
        client.find_pull_request("owner", "repo", head="octo:profile", base="master")


@pytest.mark.parametrize(
    "payload,expected",
    [([], None), ([None, "unexpected"], None), ([None, {"number": 123}, {"number": 456}], {"number": 123})],
)
def test_github_finds_first_pull_request_object(payload: list[object], expected: dict[str, int] | None) -> None:
    transport = FakeTransport([Response(200, payload)])
    client = GitHubClient("token", transport=transport)

    result = client.find_pull_request("owner", "repo", head="octo:profile", base="master")

    assert result == expected
    assert transport.calls[0]["params"] == {"state": "open", "head": "octo:profile", "base": "master"}


@pytest.mark.parametrize("payload", [{}, [], None])
def test_github_error_without_message_includes_http_status(payload: object) -> None:
    client = GitHubClient("token", transport=FakeTransport([Response(503, payload)]))

    with pytest.raises(GitHubApiError, match="failed with status 503"):
        client.fetch_authenticated_user()


@pytest.mark.parametrize("payload", [{"message": "Unexpected conflict"}, []])
def test_fork_sync_does_not_swallow_unrelated_conflicts(payload: object) -> None:
    client = GitHubClient("token", transport=FakeTransport([Response(409, payload)]))

    with pytest.raises(GitHubApiError, match="could not fetch upstream into contribution branch profile") as raised:
        client.sync_fork_branch("octo", "repo", "profile")

    assert isinstance(raised.value.__cause__, GitHubApiError)


def test_fork_sync_reports_invalid_conflict_response() -> None:
    response = Response(409, None)
    client = GitHubClient("token", transport=FakeTransport([response]))

    with (
        patch.object(response, "json", side_effect=ValueError("Invalid JSON")),
        pytest.raises(GitHubApiError, match="invalid JSON while fetching"),
    ):
        client.sync_fork_branch("octo", "repo", "profile")


@pytest.mark.parametrize("content", ["a", "not-ascii-\u2603"])
def test_file_download_reports_invalid_base64(content: str) -> None:
    client = GitHubClient(transport=FakeTransport([Response(200, {"encoding": "base64", "content": content})]))

    with pytest.raises(GitHubApiError, match=r"invalid base64 content for model\.json"):
        client.get_file("owner", "repo", "model.json", "master")


@pytest.mark.parametrize("blob", [{"encoding": "none", "content": "abc"}, {"encoding": "base64", "content": None}])
def test_large_file_download_requires_base64_blob(blob: dict[str, object]) -> None:
    client = GitHubClient(
        transport=FakeTransport(
            [
                Response(200, {"encoding": "none", "sha": "blob-sha"}),
                Response(200, blob),
            ]
        )
    )

    with pytest.raises(GitHubApiError, match=r"did not return base64 content for model\.json"):
        client.get_file("owner", "repo", "model.json", "master")


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

    user = client.fetch_authenticated_user()
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
    "environment, expected_error",
    [
        ({"POWERCALC_GITHUB_REPOSITORY": "missing-repository"}, "must use the owner/repository format"),
        ({"POWERCALC_GITHUB_REPOSITORY": "owner/repo/extra"}, "must use the owner/repository format"),
        ({"POWERCALC_GITHUB_BRANCH": "../unsafe"}, "contains an invalid branch name"),
    ],
)
def test_github_repository_rejects_invalid_environment(environment: dict[str, str], expected_error: str) -> None:
    with pytest.raises(ValueError, match=expected_error):
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


def test_github_client_reads_public_preview_references_without_token() -> None:
    encoded = base64.b64encode(b'{"ok": true}').decode()
    transport = FakeTransport(
        [
            Response(200, {"object": {"sha": "base-sha"}}),
            Response(200, {"encoding": "base64", "content": encoded}),
        ],
    )
    client = GitHubClient(transport=transport)

    assert client.get_ref("owner", "repo", "master") == {"object": {"sha": "base-sha"}}
    assert client.get_file("owner", "repo", "profile_library/library.json", "base-sha") == b'{"ok": true}'
    assert all("Authorization" not in call["headers"] for call in transport.calls)


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
        client.fetch_authenticated_user()


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
