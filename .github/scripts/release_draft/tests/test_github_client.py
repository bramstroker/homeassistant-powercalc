"""Tests for the GitHub REST client helpers."""

from typing import Any

from github_client import GitHubClient
import pytest


def test_pull_request_file_details_preserve_status(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GitHubClient("token", "owner/repo")
    changed_files: list[dict[str, Any]] = [
        {"filename": "profile_library/acme/model/model.json", "status": "added"},
    ]
    monkeypatch.setattr(client, "_paginate", lambda _path: changed_files)

    assert client.pull_request_file_details(42) == changed_files
    assert client.pull_request_files(42) == ["profile_library/acme/model/model.json"]
