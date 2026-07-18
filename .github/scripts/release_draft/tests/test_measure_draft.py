"""Behavioural tests for the rolling Measure release draft."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import update_measure_draft as entry


class FakeClient:
    def __init__(
        self,
        releases: list[dict[str, Any]],
        pull_requests: list[dict[str, Any]],
        *,
        missing_refs: set[str] | None = None,
    ) -> None:
        self._releases = releases
        self._pull_requests = pull_requests
        self._missing_refs = missing_refs or set()
        self.created: list[dict[str, Any]] = []
        self.updated: list[tuple[int, dict[str, Any]]] = []
        self.deleted: list[int] = []
        self.history_requests: list[tuple[str | None, str]] = []

    def releases(self) -> list[dict[str, Any]]:
        return self._releases

    def commit_sha(self, ref: str) -> str:
        if ref in self._missing_refs:
            raise ValueError(f"Unknown ref {ref}")
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


def pull_request(number: int, title: str, *, labels: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": label} for label in labels],
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
    entry.main([])
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


def test_release_verification_accepts_exact_changelog_notes() -> None:
    client = FakeClient([], [pull_request(10, "feat: Add measurement mode")])
    changelog = """# Changelog

## Unreleased

## 0.1.0 - 2026-07-18

### 🚀 Features

- #10 feat: Add measurement mode @octocat

## 0.0.1 - 2026-07-17

- Initial release.
"""

    entry.verify_release(client, changelog, "0.1.0", head_ref="master")

    assert client.history_requests == [("sha-of-measure-v0.0.1", "master")]


def test_release_verification_reports_intervening_missing_pull_request() -> None:
    client = FakeClient(
        [],
        [
            pull_request(10, "feat: Add measurement mode"),
            pull_request(11, "fix: Keep release notes complete"),
        ],
    )
    changelog = """# Changelog

## Unreleased

## 0.1.0 - 2026-07-18

### 🚀 Features

- #10 feat: Add measurement mode @octocat

## 0.0.1 - 2026-07-17

- Initial release.
"""

    with pytest.raises(entry.ReleaseDraftDriftError) as error:
        entry.verify_release(client, changelog, "0.1.0", head_ref="master")

    assert "out of date" in str(error.value)
    assert "#11 fix: Keep release notes complete" in str(error.value)


def test_release_verification_ignores_excluded_pull_requests() -> None:
    client = FakeClient(
        [],
        [
            pull_request(10, "feat: Add measurement mode"),
            pull_request(11, "chore: Prepare release", labels=("measure-tool", "skip-changelog")),
            pull_request(12, "chore: Update dependencies", labels=("dependencies",)),
        ],
    )
    changelog = """# Changelog

## Unreleased

## 0.1.0 - 2026-07-18

### 🚀 Features

- #10 feat: Add measurement mode @octocat

## 0.0.1 - 2026-07-17

- Initial release.
"""

    entry.verify_release(client, changelog, "0.1.0", head_ref="master")


def test_release_verification_accepts_explicit_previous_tag() -> None:
    client = FakeClient([], [pull_request(10, "fix: Correct meter probing")])
    changelog = """# Changelog

## Unreleased

## 0.1.0 - 2026-07-18

### 🐛 Bug Fixes

- #10 fix: Correct meter probing @octocat

## 0.0.1 - 2026-07-17

- Initial release.
"""

    entry.verify_release(
        client,
        changelog,
        "0.1.0",
        head_ref="release-commit",
        previous_tag="measure-v0.0.0",
    )

    assert client.history_requests == [("sha-of-measure-v0.0.0", "release-commit")]


@pytest.mark.parametrize(
    ("changelog", "message"),
    [
        ("# Changelog\n\n## Unreleased\n", "no section for target version 0.1.0"),
        (
            "# Changelog\n\n## Unreleased\n\n## 0.1.0 - 2026-07-18\n\n- Change.\n",
            "no previous Measure release after 0.1.0",
        ),
        (
            "# Changelog\n\n## Unreleased\n\n## 0.1.0 - 2026-07-18\n\n- Change.\n\n## Notes\n",
            "next changelog section after 0.1.0 is not a Measure version",
        ),
    ],
)
def test_release_verification_rejects_malformed_changelog_boundaries(changelog: str, message: str) -> None:
    with pytest.raises(entry.ReleaseDraftDriftError, match=message):
        entry.verify_release(FakeClient([], []), changelog, "0.1.0", head_ref="master")


def test_release_verification_reports_missing_previous_tag() -> None:
    changelog = """# Changelog

## Unreleased

## 0.1.0 - 2026-07-18

- Change.

## 0.0.1 - 2026-07-17

- Initial release.
"""
    client = FakeClient([], [], missing_refs={"measure-v0.0.1"})

    with pytest.raises(entry.ReleaseDraftDriftError, match=r"could not resolve previous tag measure-v0\.0\.1"):
        entry.verify_release(client, changelog, "0.1.0", head_ref="master")


def test_verify_cli_exits_nonzero_with_actionable_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## Unreleased\n\n## 0.1.0 - 2026-07-18\n\n- Stale.\n\n"
        "## 0.0.1 - 2026-07-17\n\n- Initial release.\n",
        encoding="utf-8",
    )
    client = FakeClient([], [pull_request(10, "fix: Correct release notes")])
    monkeypatch.setattr(entry, "GitHubClient", lambda *_args, **_kwargs: client)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    with pytest.raises(SystemExit, match="2"):
        entry.main(["--verify", "0.1.0", "--changelog", str(changelog), "--head-ref", "master"])

    error = capsys.readouterr().err
    assert "out of date" in error
    assert "Regenerate the release from the current rolling draft" in error
    assert "#10 fix: Correct release notes" in error
