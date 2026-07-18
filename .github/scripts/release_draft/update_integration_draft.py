#!/usr/bin/env python3
"""
Maintain the Powercalc integration draft release.

Replaces the release-drafter GitHub Action. Runs on every push to master
(stable channel) and beta (beta channel) and recomputes the relevant draft
from every pull request merged since the last stable release:

- stable: a draft tagged ``vX.Y.Z``, resolved from the merged pull requests.
- beta:   a prerelease draft tagged ``vX.Y.Z-beta.N``, where ``N`` is the next
          unpublished beta number for that core version.

The two channels own separate drafts (distinguished by the prerelease flag), so
a beta push never disturbs the stable draft and vice versa. This is the piece
release-drafter could not express with a single config.

Version resolution is conventional-commit aware and mirrors the Measure draft:
a ``!`` marker or a major/breaking label bumps major, a ``feat`` type or a
feature/enhancement/minor label bumps minor, everything else bumps patch.
Explicit major/minor/patch labels always win.

The body is recomputed from scratch on every run, so relabelling a pull request
and pushing again self-heals the draft. The Buy Me a Coffee supporters section
is generated in-process and appended as a footer; a failure to fetch it is
logged and never blocks drafting.

Requires:
- Python 3.11+ (standard library only)
- `GITHUB_TOKEN` with contents write and pull-requests read
- `GITHUB_REPOSITORY`, `CHANNEL` (stable|beta) and `HEAD_REF` (branch name)
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

from changelog import (
    UNCATEGORIZED,
    Category,
    bump,
    bump_level,
    category_title,
    format_entry,
    format_version,
    parse_core,
    render_sections,
)
from supporters import build_supporters_section
from github_client import GitHubClient

NAME_TEMPLATE = "v{version} 🌈"
EXCLUDE_LABELS = frozenset({"skip-changelog", "dependencies", "measure-tool"})

# Category order mirrors the previous release-drafter config, plus a Breaking
# Changes section that release-drafter could not populate.
CATEGORIES = [
    Category(title="💡 Power profiles", labels=frozenset({"powerprofile"})),
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

STABLE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _labels(pull_request: dict[str, Any]) -> set[str]:
    return {label["name"] for label in pull_request["labels"]}


def _qualifies(pull_request: dict[str, Any]) -> bool:
    return not _labels(pull_request) & EXCLUDE_LABELS


def _latest_stable_release(client: GitHubClient) -> dict[str, Any] | None:
    """The highest published, non-prerelease ``vX.Y.Z`` release."""
    best: dict[str, Any] | None = None
    best_version: tuple[int, int, int] | None = None
    for release in client.releases():
        if release["draft"] or release["prerelease"]:
            continue
        match = STABLE_TAG.match(release["tag_name"])
        if match is None:
            continue
        version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if best_version is None or version > best_version:
            best_version = version
            best = release
    return best


def _next_beta_number(client: GitHubClient, core: tuple[int, int, int]) -> int:
    prefix = f"v{format_version(core)}-beta."
    numbers = [
        int(release["tag_name"][len(prefix):])
        for release in client.releases()
        if not release["draft"]
        and release["tag_name"].startswith(prefix)
        and release["tag_name"][len(prefix):].isdigit()
    ]
    return max(numbers) + 1 if numbers else 0


def _find_draft(client: GitHubClient, *, prerelease: bool) -> dict[str, Any] | None:
    """The existing integration draft for the given channel, if any.

    Matched on the prerelease flag and a ``v`` tag, which keeps the two channel
    drafts apart and never touches the Measure ``measure-next`` draft.
    """
    return next(
        (
            release
            for release in client.releases()
            if release["draft"]
            and bool(release["prerelease"]) == prerelease
            and release["tag_name"].startswith("v")
        ),
        None,
    )


def _supporters_footer() -> str:
    """The supporters section; a Buy Me a Coffee outage must never block drafting."""
    try:
        return build_supporters_section()
    except Exception as error:  # noqa: BLE001 - a footer is best-effort
        print(f"Supporters section unavailable, continuing without a footer: {error}", file=sys.stderr)
        return ""


def _build_body(pull_requests: list[dict[str, Any]], footer: str) -> str:
    sections: dict[str, list[str]] = {UNCATEGORIZED: []}
    for pull_request in sorted(pull_requests, key=lambda pull_request: pull_request["number"]):
        sections.setdefault(category_title(pull_request, CATEGORIES), []).append(format_entry(pull_request))
    body = "## Changes\n\n" + render_sections(sections, SECTION_ORDER)
    if footer.strip():
        body = f"{body}\n{footer.strip()}\n"
    return body


def main() -> None:
    client = GitHubClient(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"])
    channel = os.environ.get("CHANNEL", "stable")
    head_ref = os.environ.get("HEAD_REF", "master")

    base = _latest_stable_release(client)
    if base is None:
        print("No published stable release found; nothing to draft against")
        return
    base_version = parse_core(base["tag_name"])
    base_sha = client.commit_sha(base["tag_name"])

    commit_shas = client.commit_shas_since(base_sha, head_ref)
    pull_requests = [
        pull_request for pull_request in client.merged_pull_requests(commit_shas) if _qualifies(pull_request)
    ]
    if not pull_requests:
        print(f"No changelog-worthy pull requests on {head_ref} since {base['tag_name']}")
        return

    level = max(bump_level(pull_request, CATEGORIES) for pull_request in pull_requests)
    next_core = bump(base_version, level)
    body = _build_body(pull_requests, _supporters_footer())

    if channel == "beta":
        version = f"{format_version(next_core)}-beta.{_next_beta_number(client, next_core)}"
        prerelease = True
    else:
        version = format_version(next_core)
        prerelease = False

    draft = _find_draft(client, prerelease=prerelease)
    payload = {
        "tag_name": f"v{version}",
        "name": NAME_TEMPLATE.format(version=version),
        "body": body,
        "draft": True,
        "prerelease": prerelease,
    }
    if draft is None:
        client.create_release(payload)
        print(f"Created {channel} draft v{version} with {len(pull_requests)} entries")
    else:
        client.update_release(draft["id"], payload)
        print(f"Updated {channel} draft v{version} with {len(pull_requests)} entries")


if __name__ == "__main__":
    main()
