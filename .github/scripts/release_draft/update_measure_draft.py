#!/usr/bin/env python3
"""
Maintain the rolling Powercalc Measure draft and verify prepared release notes.

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

import argparse
from collections.abc import Sequence
import difflib
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
CHANGELOG_PATH = Path("utils/measure/home-assistant-app/powercalc_measure/CHANGELOG.md")
VERSION_PATTERN = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?"

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
RELEASE_INFRASTRUCTURE_DIRECTORIES = (".github/scripts/release_draft/",)
RELEASE_INFRASTRUCTURE_FILES = frozenset(
    {
        ".github/workflows/measure-release.yml",
        ".github/workflows/prepare-measure-release.yml",
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


class ReleaseDraftDriftError(ValueError):
    """Raised when prepared release notes differ from merged Measure pull requests."""


def _touches_measure(files: list[str]) -> bool:
    return any(
        filename.startswith(MEASURE_DIRECTORIES) or filename in MEASURE_FILES
        for filename in files
    )


def _only_touches_release_infrastructure(files: list[str]) -> bool:
    return bool(files) and all(
        filename.startswith(RELEASE_INFRASTRUCTURE_DIRECTORIES) or filename in RELEASE_INFRASTRUCTURE_FILES
        for filename in files
    )


def _qualifies(client: GitHubClient, pull_request: dict[str, Any]) -> bool:
    labels = labels_of(pull_request)
    if labels & EXCLUDE_LABELS:
        return False
    files = client.pull_request_files(pull_request["number"])
    if _only_touches_release_infrastructure(files):
        return False
    return INCLUDE_LABEL in labels or _touches_measure(files)


def _qualified_pull_requests_since(
    client: GitHubClient,
    previous_tag: str,
    head_ref: str,
) -> list[dict[str, Any]]:
    try:
        base_sha = client.commit_sha(previous_tag)
    except Exception as error:
        raise ReleaseDraftDriftError(f"could not resolve previous tag {previous_tag}: {error}") from error
    commit_shas = client.commit_shas_since(base_sha, head_ref)
    return [
        pull_request
        for pull_request in client.merged_pull_requests(commit_shas)
        if _qualifies(client, pull_request)
    ]


def _render_release_notes(pull_requests: list[dict[str, Any]]) -> str:
    sections: dict[str, list[str]] = {UNCATEGORIZED: []}
    for pull_request in pull_requests:
        sections.setdefault(category_title(pull_request, CATEGORIES), []).append(format_entry(pull_request))
    return render_sections(sections, SECTION_ORDER)


def _changelog_release(changelog: str, target_version: str) -> tuple[str, str]:
    normalized = changelog.replace("\r\n", "\n")
    headings = list(re.finditer(r"^## (?P<title>.+?)[ \t]*$", normalized, re.MULTILINE))
    target_pattern = re.compile(rf"{re.escape(target_version)}(?:\s+-\s+.+)?")
    target_indexes = [
        index
        for index, heading in enumerate(headings)
        if target_pattern.fullmatch(heading.group("title"))
    ]
    if not target_indexes:
        raise ReleaseDraftDriftError(f"Changelog has no section for target version {target_version}")
    if len(target_indexes) > 1:
        raise ReleaseDraftDriftError(f"Changelog has multiple sections for target version {target_version}")

    target_index = target_indexes[0]
    if target_index + 1 >= len(headings):
        raise ReleaseDraftDriftError(f"Changelog has no previous Measure release after {target_version}")
    target = headings[target_index]
    previous = headings[target_index + 1]
    previous_match = re.fullmatch(rf"(?P<version>{VERSION_PATTERN})(?:\s+-\s+.+)?", previous.group("title"))
    if previous_match is None:
        raise ReleaseDraftDriftError(
            f"The next changelog section after {target_version} is not a Measure version: {previous.group('title')!r}",
        )
    notes = normalized[target.end() : previous.start()].strip("\r\n")
    return notes, f"measure-v{previous_match.group('version')}"


def verify_release(
    client: GitHubClient,
    changelog: str,
    target_version: str,
    *,
    head_ref: str,
    previous_tag: str | None = None,
) -> None:
    """Verify prepared changelog notes against qualifying Measure pull requests."""

    actual_notes, derived_previous_tag = _changelog_release(changelog, target_version)
    boundary_tag = previous_tag or derived_previous_tag
    if re.fullmatch(rf"measure-v{VERSION_PATTERN}", boundary_tag) is None:
        raise ReleaseDraftDriftError(f"Invalid previous Measure tag: {boundary_tag}")
    pull_requests = _qualified_pull_requests_since(client, boundary_tag, head_ref)
    expected_notes = _render_release_notes(pull_requests).strip("\r\n")
    if actual_notes == expected_notes:
        return

    difference = "\n".join(
        difflib.unified_diff(
            actual_notes.splitlines(),
            expected_notes.splitlines(),
            fromfile=f"CHANGELOG.md {target_version}",
            tofile=f"merged Measure PRs since {boundary_tag}",
            lineterm="",
        ),
    )
    raise ReleaseDraftDriftError(
        f"Measure changelog notes for {target_version} are out of date. "
        "Regenerate the release from the current rolling draft before tagging.\n"
        f"{difference}",
    )


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


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Maintain or verify the rolling Powercalc Measure release draft")
    parser.add_argument("--verify", metavar="VERSION", help="Verify a prepared changelog release before tagging")
    parser.add_argument("--previous-tag", help="Override the previous measure-v* tag derived from the changelog")
    parser.add_argument("--changelog", type=Path, default=CHANGELOG_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--head-ref", help="Git ref containing merged pull requests; defaults to HEAD_REF or master")
    args = parser.parse_args(argv)
    client = GitHubClient(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
    head_ref = args.head_ref or os.environ.get("HEAD_REF", "master")
    if args.verify is not None:
        try:
            verify_release(
                client,
                args.changelog.read_text(encoding="utf-8"),
                args.verify,
                head_ref=head_ref,
                previous_tag=args.previous_tag,
            )
        except (OSError, ReleaseDraftDriftError) as error:
            parser.error(str(error))
        print(f"Verified Measure {args.verify} notes against merged pull requests through {head_ref}")
        return

    current = _current_version()
    current_version = format_version(current)
    pull_requests = _qualified_pull_requests_since(client, f"measure-v{current_version}", head_ref)
    draft = _rolling_draft(client)
    if not pull_requests:
        if draft is not None:
            client.delete_release(draft["id"])
            print(f"Removed empty rolling draft after measure-v{current_version}")
        else:
            print(f"No merged Measure pull requests on {head_ref} since measure-v{current_version}")
        return

    levels: list[int] = []
    for pull_request in pull_requests:
        entry = format_entry(pull_request)
        levels.append(bump_level(pull_request, CATEGORIES))
        print(f"Adding {entry}")

    next_version = format_version(bump(current, max(levels)))
    payload = {
        "tag_name": DRAFT_TAG,
        "name": DRAFT_TITLE_PATTERN.format(version=next_version),
        "body": _render_release_notes(pull_requests),
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
