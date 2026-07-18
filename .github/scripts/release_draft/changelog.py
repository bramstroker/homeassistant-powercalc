"""Pure changelog logic: categorisation, semver bumping and rendering.

Nothing in this module performs I/O, so every function is deterministic and
directly unit-testable. A pull request is represented as the plain dict the
GitHub REST API returns; only the ``labels``, ``title``, ``number`` and
``user`` keys are read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

PATCH, MINOR, MAJOR = 0, 1, 2

# Explicit version labels always win over the inferred bump level.
MAJOR_LABELS = frozenset({"major", "breaking", "breaking-change"})
MINOR_LABELS = frozenset({"minor"})
PATCH_LABELS = frozenset({"patch"})

# A leading conventional-commit type, optionally scoped and optionally marked
# breaking with a trailing "!": "feat:", "fix(core):", "refactor!:".
CONVENTIONAL_TITLE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<breaking>!)?:")

VERSION_CORE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

# The uncategorised bucket is rendered first, without a heading.
UNCATEGORIZED = ""


@dataclass(frozen=True)
class Category:
    """A changelog section and the pull requests that belong in it.

    A pull request is placed in the first category (in declaration order) that
    matches one of its labels or its conventional-commit type. The ``breaking``
    category, when present, captures every breaking change regardless of the
    other rules. ``minor`` marks the category as feature-like, so a matching
    pull request bumps the minor version unless an explicit version label
    overrides it.
    """

    title: str
    labels: frozenset[str] = field(default_factory=frozenset)
    types: frozenset[str] = field(default_factory=frozenset)
    breaking: bool = False
    minor: bool = False


def labels_of(pull_request: dict[str, Any]) -> set[str]:
    return {label["name"] for label in pull_request["labels"]}


def _conventional(pull_request: dict[str, Any]) -> re.Match[str] | None:
    return CONVENTIONAL_TITLE.match(pull_request["title"].strip())


def is_breaking(pull_request: dict[str, Any]) -> bool:
    match = _conventional(pull_request)
    return bool(labels_of(pull_request) & MAJOR_LABELS or (match and match.group("breaking")))


def resolve_category(pull_request: dict[str, Any], categories: list[Category]) -> Category | None:
    """Return the category a pull request belongs to, or ``None`` when uncategorised."""
    if is_breaking(pull_request):
        for category in categories:
            if category.breaking:
                return category
    labels = labels_of(pull_request)
    for category in categories:
        if labels & category.labels:
            return category
    match = _conventional(pull_request)
    if match is not None:
        commit_type = match.group("type")
        for category in categories:
            if commit_type in category.types:
                return category
    return None


def category_title(pull_request: dict[str, Any], categories: list[Category]) -> str:
    category = resolve_category(pull_request, categories)
    return category.title if category is not None else UNCATEGORIZED


def bump_level(pull_request: dict[str, Any], categories: list[Category]) -> int:
    """Infer how far a single pull request should move the version."""
    if is_breaking(pull_request):
        return MAJOR
    labels = labels_of(pull_request)
    if labels & MINOR_LABELS:
        return MINOR
    if labels & PATCH_LABELS:
        return PATCH
    category = resolve_category(pull_request, categories)
    if category is not None and category.minor:
        return MINOR
    return PATCH


def bump(version: tuple[int, int, int], level: int) -> tuple[int, int, int]:
    major, minor, patch = version
    if level == MAJOR:
        return (major + 1, 0, 0)
    if level == MINOR:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def parse_core(text: str) -> tuple[int, int, int]:
    """Extract the first ``X.Y.Z`` core version from a tag or title."""
    match = VERSION_CORE.search(text)
    if match is None:
        raise ValueError(f"No semantic version found in {text!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def format_version(version: tuple[int, int, int]) -> str:
    return "{}.{}.{}".format(*version)


def format_entry(pull_request: dict[str, Any]) -> str:
    return f"- #{pull_request['number']} {pull_request['title'].strip()} @{pull_request['user']['login']}"


def parse_sections(body: str) -> dict[str, list[str]]:
    """Split an existing draft body back into ``{title: [entry, ...]}``.

    Level-three headings introduce a section; the leading lines without a
    heading form the uncategorised bucket.
    """
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


def render_sections(sections: dict[str, list[str]], order: list[str]) -> str:
    """Render sections in ``order``, appending any unlisted sections after it.

    The uncategorised bucket (``""``) is rendered without a heading; every other
    section gets a level-three heading. Empty sections are skipped.
    """
    ordered = list(order) + [title for title in sections if title and title not in order]
    blocks = []
    for title in ordered:
        lines = sections.get(title)
        if not lines:
            continue
        entries = "\n".join(lines)
        blocks.append(entries if title == UNCATEGORIZED else f"### {title}\n\n{entries}")
    return "\n\n".join(blocks) + "\n"
