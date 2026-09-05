"""Tests for the GitHub API client helpers."""

from typing import Any

from github_client import GitHubClient
import pytest


def test_merged_pull_requests_uses_one_batched_query(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GitHubClient("token", "owner/repo")
    requests: list[tuple[str, str, dict[str, Any] | None]] = []

    def request(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        requests.append((method, url, payload))
        pull_request = {
            "number": 42,
            "title": "fix: make drafting fast",
            "mergedAt": "2026-09-02T12:00:00Z",
            "author": {"login": "octocat"},
            "labels": {"nodes": [{"name": "bugfix"}]},
        }
        return {
            "data": {
                "repository": {
                    "commit0": {"associatedPullRequests": {"nodes": [pull_request]}},
                    "commit1": {"associatedPullRequests": {"nodes": [pull_request]}},
                    "commit2": {"associatedPullRequests": {"nodes": []}},
                },
            },
        }

    monkeypatch.setattr(client, "_request", request)

    assert client.merged_pull_requests(["sha1", "sha2", "sha3"]) == [
        {
            "number": 42,
            "title": "fix: make drafting fast",
            "merged_at": "2026-09-02T12:00:00Z",
            "user": {"login": "octocat"},
            "labels": [{"name": "bugfix"}],
        },
    ]
    assert len(requests) == 1
    assert requests[0][0:2] == ("POST", "https://api.github.com/graphql")
    assert requests[0][2] is not None
    assert requests[0][2]["variables"] == {"owner": "owner", "name": "repo"}


def test_merged_pull_requests_splits_large_histories_into_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GitHubClient("token", "owner/repo")
    requests = 0

    def request(_method: str, _url: str, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        nonlocal requests
        requests += 1
        commit_count = 50 if requests == 1 else 1
        return {
            "data": {
                "repository": {
                    f"commit{index}": {"associatedPullRequests": {"nodes": []}} for index in range(commit_count)
                },
            },
        }

    monkeypatch.setattr(client, "_request", request)

    assert client.merged_pull_requests([f"sha{index}" for index in range(51)]) == []
    assert requests == 2


def test_pull_request_file_details_preserve_status(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GitHubClient("token", "owner/repo")
    changed_files: list[dict[str, Any]] = [
        {"filename": "profile_library/acme/model/model.json", "status": "added"},
    ]
    monkeypatch.setattr(client, "_paginate", lambda _path: changed_files)

    assert client.pull_request_file_details(42) == changed_files
    assert client.pull_request_files(42) == ["profile_library/acme/model/model.json"]
