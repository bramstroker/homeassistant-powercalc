#!/usr/bin/env python3
"""
Maintain the rolling Powercalc Measure draft release.

Runs on every push to master. Each pushed commit is resolved to its merged
pull request; when that pull request touches the Measure tool, a changelog
line is appended to the body of the single rolling draft release with the
`measure-next` tag.

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
- `GITHUB_REPOSITORY` and `COMMIT_SHAS` (JSON array of pushed commit SHAs)
- a repository checkout as the working directory (reads the app config)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from changelog import (
    MAJOR,
    MINOR,
    PATCH,
    UNCATEGORIZED,
    Category,
    bump,
    bump_level,
    category_title,
    format_entry,
    format_version,
    labels_of,
    parse_sections,
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


def _pending_level(draft_name: str, current: tuple[int, int, int]) -> int:
    """Infer the bump level already accumulated in the draft from its title."""
    match = re.search(r"v(\d+)\.(\d+)\.(\d+)", draft_name)
    if match is not None:
        pending = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        for level in (MAJOR, MINOR, PATCH):
            if bump(current, level) == pending:
                return level
    return PATCH


def _rolling_draft(client: GitHubClient) -> dict[str, Any] | None:
    return next(
        (release for release in client.releases() if release["draft"] and release["tag_name"] == DRAFT_TAG),
        None,
    )


def main() -> None:
    client = GitHubClient(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
    commit_shas = json.loads(os.environ["COMMIT_SHAS"])

    pull_requests = [
        pull_request
        for pull_request in client.merged_pull_requests(commit_shas)
        if _qualifies(client, pull_request)
    ]
    if not pull_requests:
        print("No merged Measure pull requests in this push")
        return

    draft = _rolling_draft(client)
    body = draft["body"] or "" if draft is not None else ""
    sections = parse_sections(body)

    current = _current_version()
    levels = [] if draft is None else [_pending_level(draft["name"] or "", current)]
    added = 0
    for pull_request in pull_requests:
        entry = format_entry(pull_request)
        levels.append(bump_level(pull_request, CATEGORIES))
        if f"- #{pull_request['number']} " in body:
            print(f"Draft already lists #{pull_request['number']}")
            continue
        sections.setdefault(category_title(pull_request, CATEGORIES), []).append(entry)
        print(f"Adding {entry}")
        added += 1

    if not added:
        return

    next_version = format_version(bump(current, max(levels)))
    payload = {
        "tag_name": DRAFT_TAG,
        "name": DRAFT_TITLE_PATTERN.format(version=next_version),
        "body": render_sections(sections, SECTION_ORDER),
        "draft": True,
    }
    if draft is None:
        client.create_release(payload)
        print(f"Created rolling draft {DRAFT_TAG} for v{next_version} with {added} entries")
    else:
        client.update_release(draft["id"], payload)
        print(f"Updated rolling draft {DRAFT_TAG} for v{next_version} with {added} new entries")


if __name__ == "__main__":
    main()
