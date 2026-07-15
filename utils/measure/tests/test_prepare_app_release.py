from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from prepare_app_release import ReleasePreparationError, main, prepare_release, write_release
import pytest


def test_prepare_release_updates_all_app_version_sources(tmp_path: Path) -> None:
    _write_release_files(tmp_path)
    release_notes = "### Added\n\n- Live measurement state.\n\n### Fixed\n\n- Preserve **Markdown** exactly."

    changes = prepare_release(tmp_path, "0.2.0", date(2026, 7, 15), release_notes)
    write_release(changes)

    assert 'version: "0.2.0"' in _read(tmp_path, "home-assistant-app/powercalc_measure/config.yaml")
    changelog = _read(tmp_path, "home-assistant-app/powercalc_measure/CHANGELOG.md")
    assert changelog == (
        f"# Changelog\n\n## Unreleased\n\n## 0.2.0 - 2026-07-15\n\n{release_notes}\n\n## 0.1.0\n\n- Initial release.\n"
    )
    assert json.loads(_read(tmp_path, "frontend/package.json"))["version"] == "0.2.0"
    package_lock = json.loads(_read(tmp_path, "frontend/package-lock.json"))
    assert package_lock["version"] == "0.2.0"
    assert package_lock["packages"][""]["version"] == "0.2.0"


def test_prepare_release_rejects_empty_release_notes_without_writes(tmp_path: Path) -> None:
    _write_release_files(tmp_path)
    original_config = _read(tmp_path, "home-assistant-app/powercalc_measure/config.yaml")

    with pytest.raises(ReleasePreparationError, match="Release notes file is empty"):
        prepare_release(tmp_path, "0.2.0", date(2026, 7, 15), " \n\t")

    assert _read(tmp_path, "home-assistant-app/powercalc_measure/config.yaml") == original_config


def test_prepare_release_rejects_version_that_is_not_a_container_tag(tmp_path: Path) -> None:
    _write_release_files(tmp_path)

    with pytest.raises(ReleasePreparationError, match="Invalid app version"):
        prepare_release(tmp_path, "0.2.0+build.1", date(2026, 7, 15), "### Added\n\n- Change.")


@pytest.mark.parametrize("heading", ["# Release notes", "## What's changed"])
def test_prepare_release_rejects_top_level_headings(tmp_path: Path, heading: str) -> None:
    _write_release_files(tmp_path)

    with pytest.raises(ReleasePreparationError, match="level-one or level-two headings"):
        prepare_release(tmp_path, "0.2.0", date(2026, 7, 15), f"{heading}\n\n- Change")


def test_prepare_release_rejects_legacy_unreleased_notes(tmp_path: Path) -> None:
    _write_release_files(tmp_path, unreleased_notes="- Manually maintained duplicate notes.")

    with pytest.raises(ReleasePreparationError, match=r"Unreleased.*must remain empty"):
        prepare_release(tmp_path, "0.2.0", date(2026, 7, 15), "### Added\n\n- Drafted note.")


def test_prepare_release_rejects_inconsistent_current_versions(tmp_path: Path) -> None:
    _write_release_files(tmp_path, package_version="0.1.1")

    with pytest.raises(ReleasePreparationError, match="version files differ"):
        prepare_release(tmp_path, "0.2.0", date(2026, 7, 15), "### Added\n\n- Change.")


def test_dry_run_prints_diff_without_writing_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_release_files(tmp_path)
    notes_path = tmp_path / "release-notes.md"
    notes_path.write_text("### Added\n\n- Drafted note.\n", encoding="utf-8")
    original_config = _read(tmp_path, "home-assistant-app/powercalc_measure/config.yaml")

    assert (
        main(
            [
                "0.2.0",
                "--notes-file",
                str(notes_path),
                "--date",
                "2026-07-15",
                "--dry-run",
                "--root",
                str(tmp_path),
            ],
        )
        == 0
    )

    output = capsys.readouterr().out
    assert '+version: "0.2.0"' in output
    assert "+## 0.2.0 - 2026-07-15" in output
    assert "+- Drafted note." in output
    assert _read(tmp_path, "home-assistant-app/powercalc_measure/config.yaml") == original_config


def _write_release_files(
    root: Path,
    *,
    unreleased_notes: str = "",
    package_version: str = "0.1.0",
) -> None:
    _write(
        root,
        "home-assistant-app/powercalc_measure/config.yaml",
        'name: Powercalc Measure\nversion: "0.1.0"\n',
    )
    _write(
        root,
        "home-assistant-app/powercalc_measure/CHANGELOG.md",
        f"# Changelog\n\n## Unreleased\n\n{unreleased_notes}\n\n## 0.1.0\n\n- Initial release.\n",
    )
    _write_json(root, "frontend/package.json", {"name": "@powercalc/measure-app", "version": package_version})
    _write_json(
        root,
        "frontend/package-lock.json",
        {
            "name": "@powercalc/measure-app",
            "version": "0.1.0",
            "packages": {"": {"name": "@powercalc/measure-app", "version": "0.1.0"}},
        },
    )


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(root: Path, relative_path: str, content: dict[str, object]) -> None:
    _write(root, relative_path, json.dumps(content, indent=2) + "\n")


def _read(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")
