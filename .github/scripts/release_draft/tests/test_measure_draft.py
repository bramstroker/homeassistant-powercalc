"""Behavioural tests for the rolling Measure release draft."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import update_measure_draft as entry


class FakeClient:
    def __init__(self, releases: list[dict[str, Any]], pull_requests: list[dict[str, Any]]) -> None:
        self._releases = releases
        self._pull_requests = pull_requests
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[int, dict[str, Any]]] = []
        self.deleted: list[int] = []
        self.history_requests: list[tuple[str | None, str]] = []

    def releases(self) -> list[dict[str, Any]]:
        return self._releases

    def commit_sha(self, ref: str) -> str:
        return f"sha-of-{ref}"

    def commit_shas_since(self, base_sha: str | None, head_ref: str) -> list[str]:
        self.history_requests.append((base_sha, head_ref))
        return ["sha1", "sha2"]

    def merged_pull_requests(self, commit_shas: list[str]) -> list[dict[str, Any]]:
        return self._pull_requests

    def pull_request_files(self, number: int) -> list[str]:
        return ["utils/measure/measure/runner/runner.py"]

    def create_release(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created.append(payload)
        return {"id": 999, **payload}

    def update_release(self, release_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.updated.append((release_id, payload))
        return {"id": release_id, **payload}

    def delete_release(self, release_id: int) -> None:
        self.deleted.append(release_id)


def release(*, body: str = "", release_id: int = 1) -> dict[str, Any]:
    return {
        "id": release_id,
        "tag_name": "measure-next",
        "name": "Powercalc Measure v0.0.2 (unreleased)",
        "body": body,
        "draft": True,
    }


def pull_request(number: int, title: str) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "labels": [],
        "user": {"login": "octocat"},
    }


def run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, client: FakeClient) -> FakeClient:
    config = tmp_path / "config.yaml"
    config.write_text('version: "0.0.1"\n', encoding="utf-8")
    monkeypatch.setattr(entry, "CONFIG_PATH", config)
    monkeypatch.setattr(entry, "GitHubClient", lambda *_args, **_kwargs: client)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("HEAD_REF", "master")
    monkeypatch.delenv("COMMIT_SHAS", raising=False)
    entry.main()
    return client


def test_rebuilds_draft_from_all_measure_prs_since_current_tag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient(
        releases=[release(body="- #99 stale entry @octocat\n", release_id=77)],
        pull_requests=[
            pull_request(10, "Add measurement mode"),
            pull_request(11, "Fix adapter cleanup"),
        ],
    )

    run(monkeypatch, tmp_path, client)

    assert client.history_requests == [("sha-of-measure-v0.0.1", "master")]
    assert client.updated[0][0] == 77
    body = client.updated[0][1]["body"]
    assert "#10 Add measurement mode" in body
    assert "#11 Fix adapter cleanup" in body
    assert "#99 stale entry" not in body


def test_removes_stale_draft_when_tag_has_no_new_measure_prs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = FakeClient(releases=[release(release_id=77)], pull_requests=[])

    run(monkeypatch, tmp_path, client)

    assert client.deleted == [77]
    assert not client.created
    assert not client.updated
