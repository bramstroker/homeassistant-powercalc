#!/usr/bin/env python3
"""
Maintain the rolling Powercalc Measure draft release.

Runs on every push to master. The draft is rebuilt from all merged Measure
pull requests since the current ``measure-v*`` tag. Rebuilding makes retries,
queued workflow replacement, and overlapping pushes idempotent.

The draft title carries the automatically resolved next version, following
semantic versioning: breaking changes (a `!` conventional-commit marker or a
major/breaking label) bump major, features bump minor, everything else bumps
patch. Explicit `major`/`minor`/`patch` labels override the resolution. The
Prepare Measure Release workflow reads this version unless one is passed.

The draft is never published in this repository: HACS reads the published
releases of homeassistant-powercalc to resolve integration versions, so a
published `measure-v*` release would be offered to Powercalc users as an
integration update. Publishing happens in the powercalc-measure-app
repository instead, driven by the Publish Measure Docker Image workflow.

Requires:
- Python 3.11+ (standard library only)
- `GITHUB_TOKEN` with contents write and pull-requests read
- `GITHUB_REPOSITORY` and `HEAD_REF`
- a repository checkout as the working directory (reads the app config)
"""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any

from changelog import (
    UNCATEGORIZED,
    Category,
    bump,
    bump_level,
    category_title,
    format_entry,
    format_version,
    labels_of,
    render_sections,
)
from github_client import GitHubClient

DRAFT_TAG = "measure-next"
DRAFT_TITLE_PATTERN = "Powercalc Measure v{version} (unreleased)"
CONFIG_PATH = Path("utils/measure/home-assistant-app/powercalc_measure/config.yaml")

# Mirrors the measure-tool globs in .github/labeler.yml.
MEASURE_DIRECTORIES = (
    "utils/measure/",
    ".github/actions/build-measure-docker/",
)
MEASURE_FILES = frozenset(
    {
        ".github/scripts/release_draft/update_measure_draft.py",
        ".github/workflows/measure-release.yml",
        ".github/workflows/prepare-measure-release.yml",
        ".github/workflows/publish-measure-image.yml",
        ".github/workflows/test-measure.yml",
    },
)
INCLUDE_LABEL = "measure-tool"
EXCLUDE_LABELS = frozenset({"skip-changelog", "dependencies"})

CATEGORIES = [
    Category(title="💥 Breaking Changes", breaking=True),
    Category(title="🚀 Features", labels=frozenset({"feature", "enhancement"}), types=frozenset({"feat"}), minor=True),
    Category(title="🐛 Bug Fixes", labels=frozenset({"fix", "bugfix", "bug"}), types=frozenset({"fix"})),
    Category(
        title="🧰 Maintenance",
        labels=frozenset({"chore"}),
        types=frozenset({"chore", "refactor", "perf", "docs", "ci", "build", "test", "style"}),
    ),
]
SECTION_ORDER = [UNCATEGORIZED, *[category.title for category in CATEGORIES]]


def _touches_measure(client: GitHubClient, number: int) -> bool:
    return any(
        filename.startswith(MEASURE_DIRECTORIES) or filename in MEASURE_FILES
        for filename in client.pull_request_files(number)
    )


def _qualifies(client: GitHubClient, pull_request: dict[str, Any]) -> bool:
    labels = labels_of(pull_request)
    if labels & EXCLUDE_LABELS:
        return False
    return INCLUDE_LABEL in labels or _touches_measure(client, pull_request["number"])


def _current_version() -> tuple[int, int, int]:
    match = re.search(r"^version:\s*[\"']?(\d+)\.(\d+)\.(\d+)", CONFIG_PATH.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise ValueError(f"No semantic version found in {CONFIG_PATH}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _rolling_draft(client: GitHubClient) -> dict[str, Any] | None:
    return next(
        (release for release in client.releases() if release["draft"] and release["tag_name"] == DRAFT_TAG),
        None,
    )


def main() -> None:
    client = GitHubClient(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
    head_ref = os.environ.get("HEAD_REF", "master")
    current = _current_version()
    current_version = format_version(current)
    base_sha = client.commit_sha(f"measure-v{current_version}")
    commit_shas = client.commit_shas_since(base_sha, head_ref)

    pull_requests = [
        pull_request
        for pull_request in client.merged_pull_requests(commit_shas)
        if _qualifies(client, pull_request)
    ]
    draft = _rolling_draft(client)
    if not pull_requests:
        if draft is not None:
            client.delete_release(draft["id"])
            print(f"Removed empty rolling draft after measure-v{current_version}")
        else:
            print(f"No merged Measure pull requests on {head_ref} since measure-v{current_version}")
        return

    sections: dict[str, list[str]] = {UNCATEGORIZED: []}
    levels: list[int] = []
    for pull_request in pull_requests:
        entry = format_entry(pull_request)
        levels.append(bump_level(pull_request, CATEGORIES))
        sections.setdefault(category_title(pull_request, CATEGORIES), []).append(entry)
        print(f"Adding {entry}")

    next_version = format_version(bump(current, max(levels)))
    payload = {
        "tag_name": DRAFT_TAG,
        "name": DRAFT_TITLE_PATTERN.format(version=next_version),
        "body": render_sections(sections, SECTION_ORDER),
        "draft": True,
    }
    if draft is None:
        client.create_release(payload)
        print(f"Created rolling draft {DRAFT_TAG} for v{next_version} with {len(pull_requests)} entries")
    else:
        client.update_release(draft["id"], payload)
        print(f"Rebuilt rolling draft {DRAFT_TAG} for v{next_version} with {len(pull_requests)} entries")


if __name__ == "__main__":
    main()
