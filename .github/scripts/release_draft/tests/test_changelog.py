"""Unit tests for the shared changelog engine."""

from __future__ import annotations

import changelog
from changelog import (
    MAJOR,
    MINOR,
    PATCH,
    Category,
    bump,
    bump_level,
    category_title,
    format_entry,
    format_version,
    is_breaking,
    parse_core,
    parse_sections,
    render_sections,
    resolve_category,
)
import pytest

CATEGORIES = [
    Category(title="💡 Power profiles", labels=frozenset({"powerprofile"})),
    Category(title="💥 Breaking Changes", breaking=True),
    Category(title="🚀 Features", labels=frozenset({"feature", "enhancement"}), types=frozenset({"feat"}), minor=True),
    Category(title="🐛 Bug Fixes", labels=frozenset({"fix", "bugfix", "bug"}), types=frozenset({"fix"})),
    Category(title="🧰 Maintenance", labels=frozenset({"chore"}), types=frozenset({"chore", "refactor", "ci"})),
]


def pr(number: int = 1, title: str = "chore: tidy", labels: list[str] | None = None, author: str = "octocat") -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": name} for name in (labels or [])],
        "user": {"login": author},
    }


# --- categorisation --------------------------------------------------------


def test_label_beats_conventional_type_and_respects_order() -> None:
    # powerprofile is declared before Features, so it wins even with a feat title.
    assert category_title(pr(title="feat: new bulb", labels=["powerprofile", "feature"]), CATEGORIES) == "💡 Power profiles"


def test_conventional_type_used_when_no_label_matches() -> None:
    assert category_title(pr(title="fix: crash on start"), CATEGORIES) == "🐛 Bug Fixes"
    assert category_title(pr(title="feat: add sensor"), CATEGORIES) == "🚀 Features"
    assert category_title(pr(title="refactor(core): cleanup"), CATEGORIES) == "🧰 Maintenance"


def test_unknown_type_is_uncategorised() -> None:
    assert category_title(pr(title="wip: something"), CATEGORIES) == ""
    assert category_title(pr(title="no conventional prefix here"), CATEGORIES) == ""


def test_breaking_wins_over_everything() -> None:
    assert resolve_category(pr(title="feat!: drop legacy", labels=["feature"]), CATEGORIES).title == "💥 Breaking Changes"
    assert resolve_category(pr(title="fix: x", labels=["breaking"]), CATEGORIES).title == "💥 Breaking Changes"


@pytest.mark.parametrize(
    ("title", "labels", "breaking"),
    [
        ("feat!: x", [], True),
        ("fix(core)!: x", [], True),
        ("feat: x", ["major"], True),
        ("feat: x", ["breaking-change"], True),
        ("feat: x", [], False),
        ("chore: x", [], False),
    ],
)
def test_is_breaking(title: str, labels: list[str], breaking: bool) -> None:
    assert is_breaking(pr(title=title, labels=labels)) is breaking


# --- version bumping -------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "labels", "level"),
    [
        ("feat!: x", [], MAJOR),
        ("feat: x", ["breaking"], MAJOR),
        ("feat: x", [], MINOR),
        ("fix: x", [], PATCH),
        ("chore: x", [], PATCH),
        ("docs: x", ["minor"], MINOR),  # explicit label overrides
        ("feat: x", ["patch"], PATCH),  # explicit label overrides feature minor
        ("random title", [], PATCH),
    ],
)
def test_bump_level(title: str, labels: list[str], level: int) -> None:
    assert bump_level(pr(title=title, labels=labels), CATEGORIES) == level


def test_powerprofile_does_not_bump_minor_by_itself() -> None:
    assert bump_level(pr(title="add profile", labels=["powerprofile"]), CATEGORIES) == PATCH


@pytest.mark.parametrize(
    ("version", "level", "expected"),
    [
        ((1, 2, 3), PATCH, (1, 2, 4)),
        ((1, 2, 3), MINOR, (1, 3, 0)),
        ((1, 2, 3), MAJOR, (2, 0, 0)),
    ],
)
def test_bump(version: tuple[int, int, int], level: int, expected: tuple[int, int, int]) -> None:
    assert bump(version, level) == expected


def test_parse_core() -> None:
    assert parse_core("v1.22.0") == (1, 22, 0)
    assert parse_core("v1.22.0-beta.3") == (1, 22, 0)
    assert parse_core("Powercalc Measure v0.4.1 (unreleased)") == (0, 4, 1)
    with pytest.raises(ValueError, match="No semantic version"):
        parse_core("no version here")


def test_format_version() -> None:
    assert format_version((1, 22, 0)) == "1.22.0"


# --- entry formatting & rendering -----------------------------------------


def test_format_entry() -> None:
    assert format_entry(pr(number=42, title="  feat: thing  ", author="alice")) == "- #42 feat: thing @alice"


def test_render_orders_sections_and_omits_empty() -> None:
    order = [changelog.UNCATEGORIZED, "🚀 Features", "🐛 Bug Fixes"]
    sections = {
        "🐛 Bug Fixes": ["- #2 fix @b"],
        changelog.UNCATEGORIZED: ["- #1 misc @a"],
        "🚀 Features": [],  # empty -> skipped
    }
    rendered = render_sections(sections, order)
    assert rendered == "- #1 misc @a\n\n### 🐛 Bug Fixes\n\n- #2 fix @b\n"


def test_render_appends_unlisted_sections_after_known_order() -> None:
    order = [changelog.UNCATEGORIZED, "🚀 Features"]
    sections = {"🚀 Features": ["- #1 a @x"], "Custom": ["- #2 b @y"]}
    rendered = render_sections(sections, order)
    assert rendered == "### 🚀 Features\n\n- #1 a @x\n\n### Custom\n\n- #2 b @y\n"


def test_parse_render_round_trip() -> None:
    body = "- #1 misc @a\n\n### 🚀 Features\n\n- #2 feat @b\n"
    order = [changelog.UNCATEGORIZED, "🚀 Features"]
    assert render_sections(parse_sections(body), order) == body


def test_parse_sections_handles_crlf_and_blank_lines() -> None:
    body = "- #1 a @x\r\n\r\n### 🐛 Bug Fixes\r\n\r\n- #2 b @y\r\n"
    sections = parse_sections(body)
    assert sections[changelog.UNCATEGORIZED] == ["- #1 a @x"]
    assert sections["🐛 Bug Fixes"] == ["- #2 b @y"]
