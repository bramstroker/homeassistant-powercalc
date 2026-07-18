"""Behavioural tests for the integration draft entry point.

A fake GitHub client stands in for the REST API so the channel, versioning and
draft-selection logic can be exercised without any network access.
"""

from __future__ import annotations

from typing import Any

import pytest
import update_integration_draft as entry


class FakeClient:
    def __init__(self, releases: list[dict[str, Any]], pull_requests: list[dict[str, Any]]) -> None:
        self._releases = releases
        self._pull_requests = pull_requests
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[int, dict[str, Any]]] = []

    def releases(self) -> list[dict[str, Any]]:
        return self._releases

    def commit_sha(self, ref: str) -> str:
        return f"sha-of-{ref}"

    def commit_shas_since(self, base_sha: str | None, head_ref: str) -> list[str]:  # noqa: ARG002
        return ["sha1", "sha2"]

    def merged_pull_requests(self, commit_shas: list[str]) -> list[dict[str, Any]]:  # noqa: ARG002
        return self._pull_requests

    def create_release(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created.append(payload)
        return {"id": 999, **payload}

    def update_release(self, release_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.updated.append((release_id, payload))
        return {"id": release_id, **payload}


def release(tag: str, *, draft: bool = False, prerelease: bool = False, release_id: int = 1) -> dict[str, Any]:
    return {"id": release_id, "tag_name": tag, "draft": draft, "prerelease": prerelease}


def pr(number: int, title: str, labels: list[str] | None = None, author: str = "octocat") -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": name} for name in (labels or [])],
        "user": {"login": author},
    }


def run(monkeypatch: pytest.MonkeyPatch, client: FakeClient, channel: str, head_ref: str) -> FakeClient:
    monkeypatch.setattr(entry, "GitHubClient", lambda *_args, **_kwargs: client)
    # Never reach the network for the supporters section during tests.
    monkeypatch.setattr(entry, "build_supporters_section", lambda: "")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("CHANNEL", channel)
    monkeypatch.setenv("HEAD_REF", head_ref)
    entry.main()
    return client


def test_stable_creates_draft_and_resolves_minor(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        releases=[release("v1.22.0"), release("v1.21.0")],
        pull_requests=[pr(10, "feat: add sensor"), pr(11, "fix: crash")],
    )
    run(monkeypatch, client, channel="stable", head_ref="master")

    assert len(client.created) == 1
    payload = client.created[0]
    assert payload["tag_name"] == "v1.23.0"  # minor bump off latest stable
    assert payload["prerelease"] is False
    assert payload["draft"] is True
    assert "### 🚀 Features" in payload["body"]
    assert "- #10 feat: add sensor @octocat" in payload["body"]


def test_stable_updates_existing_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        releases=[release("v1.22.0"), release("v1.23.0", draft=True, release_id=77)],
        pull_requests=[pr(10, "fix: crash")],
    )
    run(monkeypatch, client, channel="stable", head_ref="master")

    assert not client.created
    assert client.updated[0][0] == 77
    assert client.updated[0][1]["tag_name"] == "v1.22.1"  # patch bump


def test_beta_creates_prerelease_with_first_beta_number(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        releases=[release("v1.22.0")],
        pull_requests=[pr(10, "feat: add sensor")],
    )
    run(monkeypatch, client, channel="beta", head_ref="beta")

    payload = client.created[0]
    assert payload["tag_name"] == "v1.23.0-beta.0"
    assert payload["prerelease"] is True


def test_beta_number_increments_past_published_betas(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        releases=[release("v1.22.0"), release("v1.23.0-beta.0", prerelease=True)],
        pull_requests=[pr(10, "feat: add sensor")],
    )
    run(monkeypatch, client, channel="beta", head_ref="beta")

    assert client.created[0]["tag_name"] == "v1.23.0-beta.1"


def test_channels_do_not_touch_each_others_drafts(monkeypatch: pytest.MonkeyPatch) -> None:
    # A beta draft exists; a stable push must create a new stable draft, not update the beta one.
    client = FakeClient(
        releases=[release("v1.22.0"), release("v1.23.0-beta.0", draft=True, prerelease=True, release_id=55)],
        pull_requests=[pr(10, "feat: add sensor")],
    )
    run(monkeypatch, client, channel="stable", head_ref="master")

    assert not client.updated
    assert client.created[0]["prerelease"] is False


def test_excluded_labels_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        releases=[release("v1.22.0")],
        pull_requests=[
            pr(10, "chore: bump dep", labels=["dependencies"]),
            pr(11, "feat: measure thing", labels=["measure-tool"]),
            pr(12, "docs: internal", labels=["skip-changelog"]),
        ],
    )
    run(monkeypatch, client, channel="stable", head_ref="master")

    # Every PR is excluded, so nothing is drafted.
    assert not client.created
    assert not client.updated


def test_generated_supporters_footer_is_appended(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(releases=[release("v1.22.0")], pull_requests=[pr(10, "fix: x")])
    monkeypatch.setattr(entry, "GitHubClient", lambda *_a, **_k: client)
    monkeypatch.setattr(entry, "build_supporters_section", lambda: "## Supporters\n\nAlice\n")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("CHANNEL", "stable")
    monkeypatch.setenv("HEAD_REF", "master")
    entry.main()

    assert client.created[0]["body"].endswith("## Supporters\n\nAlice\n")


def test_supporters_failure_does_not_block_drafting(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(releases=[release("v1.22.0")], pull_requests=[pr(10, "fix: x")])
    monkeypatch.setattr(entry, "GitHubClient", lambda *_a, **_k: client)

    def boom() -> str:
        raise RuntimeError("BMC down")

    monkeypatch.setattr(entry, "build_supporters_section", boom)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("CHANNEL", "stable")
    monkeypatch.setenv("HEAD_REF", "master")
    entry.main()

    assert client.created[0]["tag_name"] == "v1.22.1"
    assert "## Changes" in client.created[0]["body"]


def test_no_stable_release_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(releases=[release("v1.0.0-beta.0", prerelease=True)], pull_requests=[pr(10, "fix: x")])
    run(monkeypatch, client, channel="stable", head_ref="master")
    assert not client.created and not client.updated
