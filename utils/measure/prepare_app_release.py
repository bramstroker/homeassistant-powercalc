#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, date, datetime
import difflib
import json
from pathlib import Path
import re
from typing import Any, cast

MEASURE_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path("home-assistant-app/powercalc_measure/config.yaml")
CHANGELOG_PATH = Path("home-assistant-app/powercalc_measure/CHANGELOG.md")
PACKAGE_PATH = Path("frontend/package.json")
PACKAGE_LOCK_PATH = Path("frontend/package-lock.json")
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?")
CONFIG_VERSION_PATTERN = re.compile(
    rf"^(?P<prefix>version:\s*)(?P<quote>[\"']?)(?P<version>{VERSION_PATTERN.pattern})(?P=quote)\s*$",
    re.MULTILINE,
)


class ReleasePreparationError(ValueError):
    """Raised when the app release inputs are incomplete or inconsistent."""


def prepare_release(root: Path, version: str, release_date: date) -> dict[Path, str]:
    """Validate and prepare every file changed by an app release."""

    if VERSION_PATTERN.fullmatch(version) is None:
        raise ReleasePreparationError(f"Invalid app version: {version}")

    config_path = root / CONFIG_PATH
    changelog_path = root / CHANGELOG_PATH
    package_path = root / PACKAGE_PATH
    package_lock_path = root / PACKAGE_LOCK_PATH

    config = config_path.read_text(encoding="utf-8")
    current_version, updated_config = _update_config_version(config, version)
    if version == current_version:
        raise ReleasePreparationError(f"App version is already {version}")

    package = _read_json(package_path)
    package_lock = _read_json(package_lock_path)
    _validate_current_versions(current_version, package, package_lock)

    changelog = changelog_path.read_text(encoding="utf-8")
    updated_changelog = _promote_changelog(changelog, current_version, version, release_date)
    package["version"] = version
    package_lock["version"] = version
    package_lock_root = _package_lock_root(package_lock)
    package_lock_root["version"] = version

    return {
        config_path: updated_config,
        changelog_path: updated_changelog,
        package_path: _format_json(package),
        package_lock_path: _format_json(package_lock),
    }


def write_release(changes: dict[Path, str]) -> None:
    """Write a fully validated set of release changes."""

    for path, content in changes.items():
        path.write_text(content, encoding="utf-8")


def _update_config_version(config: str, version: str) -> tuple[str, str]:
    matches = list(CONFIG_VERSION_PATTERN.finditer(config))
    if len(matches) != 1:
        raise ReleasePreparationError("App config must contain exactly one semantic version")

    match = matches[0]
    current_version = match.group("version")
    replacement = f"{match.group('prefix')}{match.group('quote')}{version}{match.group('quote')}"
    return current_version, config[: match.start()] + replacement + config[match.end() :]


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ReleasePreparationError(f"Expected a JSON object in {path}")
    return data


def _validate_current_versions(
    current_version: str,
    package: dict[str, Any],
    package_lock: dict[str, Any],
) -> None:
    versions = {
        "frontend/package.json": package.get("version"),
        "frontend/package-lock.json": package_lock.get("version"),
        "frontend/package-lock.json packages['']": _package_lock_root(package_lock).get("version"),
    }
    mismatches = [f"{source}={version!r}" for source, version in versions.items() if version != current_version]
    if mismatches:
        raise ReleasePreparationError(
            f"Current app version is {current_version}, but version files differ: {', '.join(mismatches)}",
        )


def _package_lock_root(package_lock: dict[str, Any]) -> dict[str, Any]:
    packages = package_lock.get("packages")
    if not isinstance(packages, dict):
        raise ReleasePreparationError("frontend/package-lock.json has no root package")
    root_package = packages.get("")
    if not isinstance(root_package, dict):
        raise ReleasePreparationError("frontend/package-lock.json has no root package")
    return cast(dict[str, Any], root_package)


def _promote_changelog(changelog: str, current_version: str, version: str, release_date: date) -> str:
    if re.search(rf"^## {re.escape(current_version)}(?:\s|$)", changelog, re.MULTILINE) is None:
        raise ReleasePreparationError(f"Changelog has no section for current version {current_version}")
    if re.search(rf"^## {re.escape(version)}(?:\s|$)", changelog, re.MULTILINE) is not None:
        raise ReleasePreparationError(f"Changelog already contains version {version}")

    unreleased_matches = list(re.finditer(r"^## Unreleased\s*$", changelog, re.MULTILINE))
    if len(unreleased_matches) != 1:
        raise ReleasePreparationError("Changelog must contain exactly one '## Unreleased' section")

    unreleased = unreleased_matches[0]
    body_start = unreleased.end()
    next_section = re.search(r"^## ", changelog[body_start:], re.MULTILINE)
    if next_section is None:
        raise ReleasePreparationError("Changelog has no released version after '## Unreleased'")

    body_end = body_start + next_section.start()
    release_notes = changelog[body_start:body_end].strip()
    if not release_notes:
        raise ReleasePreparationError("Add release notes below '## Unreleased' before preparing a release")

    promoted = f"## Unreleased\n\n## {version} - {release_date.isoformat()}\n\n{release_notes}\n\n"
    return changelog[: unreleased.start()] + promoted + changelog[body_end:]


def _format_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _print_diff(changes: dict[Path, str], root: Path) -> None:
    for path, updated in changes.items():
        original = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(root)
        print(
            "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    updated.splitlines(keepends=True),
                    fromfile=str(relative_path),
                    tofile=str(relative_path),
                ),
            ),
            end="",
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a Powercalc Measure Home Assistant app release")
    parser.add_argument("version", help="New semantic version, for example 0.2.0")
    parser.add_argument(
        "--date",
        default=datetime.now(UTC).date().isoformat(),
        help="Release date in YYYY-MM-DD format",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show the changes without writing files")
    parser.add_argument("--root", type=Path, default=MEASURE_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        release_date = date.fromisoformat(args.date)
        changes = prepare_release(args.root.resolve(), args.version, release_date)
    except (ReleasePreparationError, ValueError, OSError, json.JSONDecodeError) as error:
        parser.error(str(error))

    if args.dry_run:
        _print_diff(changes, args.root.resolve())
        return 0

    write_release(changes)
    print(f"Prepared Powercalc Measure app release {args.version}")
    for path in changes:
        print(f"- {path.relative_to(args.root.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
