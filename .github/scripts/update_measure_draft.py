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
import urllib.request

API_ROOT = "https://api.github.com"
DRAFT_TAG = "measure-next"
DRAFT_TITLE_PATTERN = "Powercalc Measure v{version} (unreleased)"
CONFIG_PATH = Path("utils/measure/home-assistant-app/powercalc_measure/config.yaml")
PAGE_SIZE = 100

# Mirrors the measure-tool globs in .github/labeler.yml.
MEASURE_DIRECTORIES = (
    "utils/measure/",
    ".github/actions/build-measure-docker/",
)
MEASURE_FILES = frozenset(
    {
        ".github/scripts/update_measure_draft.py",
        ".github/workflows/measure-release.yml",
        ".github/workflows/prepare-measure-release.yml",
        ".github/workflows/publish-measure-image.yml",
        ".github/workflows/test-measure.yml",
    },
)
INCLUDE_LABEL = "measure-tool"
EXCLUDE_LABELS = frozenset({"skip-changelog", "dependencies"})

PATCH, MINOR, MAJOR = 0, 1, 2
MAJOR_LABELS = frozenset({"major", "breaking", "breaking-change"})
MINOR_LABELS = frozenset({"minor"})
PATCH_LABELS = frozenset({"patch"})
FEATURE_LABELS = frozenset({"feature", "enhancement"})
FIX_LABELS = frozenset({"fix", "bugfix", "bug"})
MAINTENANCE_LABELS = frozenset({"chore"})
CONVENTIONAL_TITLE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<breaking>!)?:")
MAINTENANCE_TYPES = frozenset({"chore", "refactor", "perf", "docs", "ci", "build", "test", "style"})

# Section rendering order. Pull requests without a recognized label or
# conventional-commit type are listed first without a heading.
UNCATEGORIZED = ""
BREAKING = "💥 Breaking Changes"
FEATURES = "🚀 Features"
FIXES = "🐛 Bug Fixes"
MAINTENANCE = "🧰 Maintenance"
SECTION_ORDER = (UNCATEGORIZED, BREAKING, FEATURES, FIXES, MAINTENANCE)


def _request(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(  # noqa: S310 - fixed https API root
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request) as response:  # noqa: S310
        body = response.read()
    return json.loads(body) if body else None


def _paginate(url: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        chunk = _request("GET", f"{url}{'&' if '?' in url else '?'}per_page={PAGE_SIZE}&page={page}")
        items.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            return items
        page += 1


def _merged_pull_requests(repository: str, commit_shas: list[str]) -> list[dict[str, Any]]:
    pull_requests: dict[int, dict[str, Any]] = {}
    for sha in commit_shas:
        for pull_request in _request("GET", f"{API_ROOT}/repos/{repository}/commits/{sha}/pulls"):
            if pull_request.get("merged_at") is not None:
                pull_requests.setdefault(pull_request["number"], pull_request)
    return [pull_requests[number] for number in sorted(pull_requests)]


def _touches_measure(repository: str, number: int) -> bool:
    files = _paginate(f"{API_ROOT}/repos/{repository}/pulls/{number}/files")
    return any(
        filename.startswith(MEASURE_DIRECTORIES) or filename in MEASURE_FILES
        for filename in (changed_file["filename"] for changed_file in files)
    )


def _qualifies(repository: str, pull_request: dict[str, Any]) -> bool:
    labels = _labels(pull_request)
    if labels & EXCLUDE_LABELS:
        return False
    return INCLUDE_LABEL in labels or _touches_measure(repository, pull_request["number"])


def _labels(pull_request: dict[str, Any]) -> set[str]:
    return {label["name"] for label in pull_request["labels"]}


def _is_breaking(pull_request: dict[str, Any]) -> bool:
    match = CONVENTIONAL_TITLE.match(pull_request["title"].strip())
    return bool(_labels(pull_request) & MAJOR_LABELS or (match and match.group("breaking")))


def _category(pull_request: dict[str, Any]) -> str:
    if _is_breaking(pull_request):
        return BREAKING
    labels = _labels(pull_request)
    if labels & FEATURE_LABELS:
        return FEATURES
    if labels & FIX_LABELS:
        return FIXES
    if labels & MAINTENANCE_LABELS:
        return MAINTENANCE
    match = CONVENTIONAL_TITLE.match(pull_request["title"].strip())
    if match is None:
        return UNCATEGORIZED
    if match.group("type") == "feat":
        return FEATURES
    if match.group("type") == "fix":
        return FIXES
    if match.group("type") in MAINTENANCE_TYPES:
        return MAINTENANCE
    return UNCATEGORIZED


def _bump_level(pull_request: dict[str, Any]) -> int:
    if _is_breaking(pull_request):
        return MAJOR
    labels = _labels(pull_request)
    if labels & MINOR_LABELS:
        return MINOR
    if labels & PATCH_LABELS:
        return PATCH
    if _category(pull_request) == FEATURES:
        return MINOR
    return PATCH


def _current_version() -> tuple[int, int, int]:
    match = re.search(r"^version:\s*[\"']?(\d+)\.(\d+)\.(\d+)", CONFIG_PATH.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise ValueError(f"No semantic version found in {CONFIG_PATH}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _bump(version: tuple[int, int, int], level: int) -> tuple[int, int, int]:
    major, minor, patch = version
    if level == MAJOR:
        return (major + 1, 0, 0)
    if level == MINOR:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def _pending_level(draft_name: str, current: tuple[int, int, int]) -> int:
    """Infer the bump level already accumulated in the draft from its title."""
    match = re.search(r"v(\d+)\.(\d+)\.(\d+)", draft_name)
    if match is not None:
        pending = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        for level in (MAJOR, MINOR, PATCH):
            if _bump(current, level) == pending:
                return level
    return PATCH


def _parse_sections(body: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {UNCATEGORIZED: []}
    current = UNCATEGORIZED
    for line in body.replace("\r\n", "\n").splitlines():
        heading = re.fullmatch(r"### (.+?)\s*", line)
        if heading is not None:
            current = heading.group(1)
            sections.setdefault(current, [])
        elif line.strip():
            sections[current].append(line.rstrip())
    return sections


def _render_sections(sections: dict[str, list[str]]) -> str:
    ordered = list(SECTION_ORDER) + [title for title in sections if title not in SECTION_ORDER]
    blocks = []
    for title in ordered:
        lines = sections.get(title)
        if not lines:
            continue
        entries = "\n".join(lines)
        blocks.append(entries if title == UNCATEGORIZED else f"### {title}\n\n{entries}")
    return "\n\n".join(blocks) + "\n"


def _rolling_draft(repository: str) -> dict[str, Any] | None:
    releases = _paginate(f"{API_ROOT}/repos/{repository}/releases")
    return next(
        (release for release in releases if release["draft"] and release["tag_name"] == DRAFT_TAG),
        None,
    )


def main() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    commit_shas = json.loads(os.environ["COMMIT_SHAS"])

    pull_requests = [
        pull_request
        for pull_request in _merged_pull_requests(repository, commit_shas)
        if _qualifies(repository, pull_request)
    ]
    if not pull_requests:
        print("No merged Measure pull requests in this push")
        return

    draft = _rolling_draft(repository)
    body = draft["body"] or "" if draft is not None else ""
    sections = _parse_sections(body)

    current = _current_version()
    levels = [] if draft is None else [_pending_level(draft["name"] or "", current)]
    added = 0
    for pull_request in pull_requests:
        entry = f"- #{pull_request['number']} {pull_request['title'].strip()} @{pull_request['user']['login']}"
        levels.append(_bump_level(pull_request))
        if f"- #{pull_request['number']} " in body:
            print(f"Draft already lists #{pull_request['number']}")
            continue
        sections.setdefault(_category(pull_request), []).append(entry)
        print(f"Adding {entry}")
        added += 1

    if not added:
        return

    next_version = "{}.{}.{}".format(*_bump(current, max(levels)))
    payload = {
        "tag_name": DRAFT_TAG,
        "name": DRAFT_TITLE_PATTERN.format(version=next_version),
        "body": _render_sections(sections),
        "draft": True,
    }
    if draft is None:
        _request("POST", f"{API_ROOT}/repos/{repository}/releases", payload)
        print(f"Created rolling draft {DRAFT_TAG} for v{next_version} with {added} entries")
    else:
        _request("PATCH", f"{API_ROOT}/repos/{repository}/releases/{draft['id']}", payload)
        print(f"Updated rolling draft {DRAFT_TAG} for v{next_version} with {added} new entries")


if __name__ == "__main__":
    main()
