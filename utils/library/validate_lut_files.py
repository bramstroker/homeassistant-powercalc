"""Validate the structure of the LUT CSV files in the profile library.

Checks every column of every LUT row against the rules for its color mode, verifies the
measurements reach the top of the brightness range and verifies each profile exposes a
color mode combination Home Assistant can actually report.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
import csv
from dataclasses import dataclass, field
from pathlib import Path

from utils.library.common import PROFILE_DIRECTORY, open_lut_file

# Measurements that stop below this brightness level were most likely aborted halfway.
MIN_MAX_BRIGHTNESS = 250
# Cap the row errors reported per file, a broken LUT would otherwise flood the output.
MAX_ERRORS_PER_FILE = 5
LUT_SUFFIXES = (".csv.gz", ".csv")

VALID_COLOR_MODE_COMBINATIONS: tuple[frozenset[str], ...] = (
    frozenset({"brightness"}),
    frozenset({"color_temp"}),
    frozenset({"hs"}),
    frozenset({"color_temp", "hs"}),
    # The combinations below are not really valid according to the HA docs, but some core
    # integrations in HA supply them (for example TP-Link).
    frozenset({"brightness", "hs"}),
    frozenset({"brightness", "color_temp"}),
    frozenset({"brightness", "color_temp", "hs"}),
)
# Effect LUTs sit next to the color mode LUTs, but effect is not a HA color mode itself,
# so it must not take part in the color mode combination check.
COMBINATION_EXEMPT_MODES = frozenset({"effect"})


@dataclass(frozen=True)
class ColumnRule:
    """Validation rule for a single LUT column."""

    name: str
    kind: str
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, value: str) -> str | None:
        """Return an error message when the raw CSV value violates this rule."""
        if self.kind == "string":
            return None if value else f"'{self.name}' is empty"

        try:
            number = int(value) if self.kind == "integer" else float(value)
        except ValueError:
            return f"'{self.name}' value '{value}' is not a valid {self.kind}"

        if self.minimum is not None and number < self.minimum:
            return f"'{self.name}' value {number} is less than minimum {self.minimum}"

        if self.maximum is not None and number > self.maximum:
            return f"'{self.name}' value {number} is greater than maximum {self.maximum}"

        return None


BRI_RULE = ColumnRule("bri", "integer", minimum=0, maximum=255)
WATT_RULE = ColumnRule("watt", "number", minimum=0.01)
# 1000 mired is 1000 K, the lowest color temperature any light on the market reaches.
MIRED_RULE = ColumnRule("mired", "integer", minimum=0, maximum=1000)
HUE_RULE = ColumnRule("hue", "integer", minimum=0, maximum=65535)
SAT_RULE = ColumnRule("sat", "integer", minimum=0, maximum=255)
EFFECT_RULE = ColumnRule("effect", "string")

COLOR_MODE_RULES: dict[str, tuple[ColumnRule, ...]] = {
    "brightness": (BRI_RULE, WATT_RULE),
    "color_temp": (BRI_RULE, MIRED_RULE, WATT_RULE),
    "hs": (BRI_RULE, HUE_RULE, SAT_RULE, WATT_RULE),
    "effect": (EFFECT_RULE, BRI_RULE, WATT_RULE),
}


@dataclass(frozen=True)
class LutValidationError:
    """A single problem found in a profile, optionally tied to one color mode."""

    profile: str
    message: str
    color_mode: str | None = None

    def __str__(self) -> str:
        if self.color_mode is None:
            return f"{self.profile}: {self.message}"

        return f"{self.profile} - {self.color_mode}: {self.message}"


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of validating a set of profiles."""

    profiles: int = 0
    files: int = 0
    errors: list[LutValidationError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def get_color_mode(path: Path) -> str | None:
    """Return the color mode a LUT file holds, or None when it is not a known LUT file."""
    for suffix in LUT_SUFFIXES:
        if path.name.endswith(suffix):
            color_mode = path.name[: -len(suffix)]
            return color_mode if color_mode in COLOR_MODE_RULES else None

    return None


def find_profile_directories(root: Path) -> list[Path]:
    """Return every directory below root that directly contains LUT files."""
    return sorted(
        {path.parent for suffix in LUT_SUFFIXES for path in root.rglob(f"*{suffix}") if get_color_mode(path)},
    )


def find_lut_files(directory: Path) -> list[tuple[Path, str]]:
    """Return the LUT files directly inside a directory, paired with their color mode."""
    lut_files = []
    for path in directory.iterdir():
        color_mode = get_color_mode(path)
        if color_mode:
            lut_files.append((path, color_mode))

    return sorted(lut_files, key=lambda entry: entry[1])


def validate_library(root: Path) -> ValidationReport:
    """Validate every profile below root."""
    profiles = find_profile_directories(root)
    files = 0
    errors: list[LutValidationError] = []
    for directory in profiles:
        profile_files, profile_errors = validate_profile(directory, root)
        files += profile_files
        errors.extend(profile_errors)

    return ValidationReport(profiles=len(profiles), files=files, errors=errors)


def validate_profile(directory: Path, root: Path) -> tuple[int, list[LutValidationError]]:
    """Validate all LUT files of a single profile and its color mode combination."""
    profile = directory.relative_to(root).as_posix()
    lut_files = find_lut_files(directory)
    errors = [
        LutValidationError(profile=profile, message=message, color_mode=color_mode)
        for path, color_mode in lut_files
        for message in validate_lut_file(path, color_mode)
    ]

    combination_error = validate_color_modes(color_mode for _, color_mode in lut_files)
    if combination_error:
        errors.append(LutValidationError(profile=profile, message=combination_error))

    return len(lut_files), errors


def validate_lut_file(path: Path, color_mode: str) -> list[str]:
    """Validate a single LUT file and return the problems found."""
    rules = COLOR_MODE_RULES[color_mode]
    with open_lut_file(path) as lut_file:
        reader = csv.DictReader(lut_file)
        missing_columns = [rule.name for rule in rules if rule.name not in (reader.fieldnames or [])]
        if missing_columns:
            return [f"missing required columns: {', '.join(missing_columns)}"]

        errors: list[str] = []
        suppressed = 0
        brightness_values: list[int] = []
        for line_number, row in enumerate(reader, start=2):
            for message in validate_row(row, rules):
                if len(errors) < MAX_ERRORS_PER_FILE:
                    errors.append(f"row {line_number}: {message}")
                else:
                    suppressed += 1

            brightness = parse_int(row.get("bri"))
            if brightness is not None:
                brightness_values.append(brightness)

    if suppressed:
        errors.append(f"... and {suppressed} more row errors")

    errors.extend(validate_max_brightness(brightness_values))

    return errors


def validate_row(row: Mapping[str, str | None], rules: Sequence[ColumnRule]) -> list[str]:
    """Validate a single LUT row against the rules of its color mode."""
    messages = []
    for rule in rules:
        value = row.get(rule.name)
        if value is None:
            messages.append(f"'{rule.name}' is missing")
            continue

        message = rule.validate(value)
        if message:
            messages.append(message)

    return messages


def validate_max_brightness(brightness_values: Sequence[int]) -> list[str]:
    """Verify the measurements reached the top of the brightness range."""
    if not brightness_values:
        return ["file contains no data rows"]

    max_brightness = max(brightness_values)
    if max_brightness < MIN_MAX_BRIGHTNESS:
        message = (
            f"max brightness level {max_brightness} is less than {MIN_MAX_BRIGHTNESS}, "
            f"measurements probably not finished completely"
        )
        return [message]

    return []


def validate_color_modes(color_modes: Iterable[str]) -> str | None:
    """Verify a profile exposes a color mode combination Home Assistant can report."""
    combination = frozenset(color_modes) - COMBINATION_EXEMPT_MODES
    if not combination or combination in VALID_COLOR_MODE_COMBINATIONS:
        return None

    return f"invalid color mode combination {','.join(sorted(combination))}"


def parse_int(value: str | None) -> int | None:
    """Parse an integer, returning None when the value is absent or malformed."""
    if value is None:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def format_report(report: ValidationReport) -> str:
    """Render the validation outcome as human readable text."""
    lines = [f"Validated {report.files} LUT files in {report.profiles} profiles."]
    if not report.has_errors:
        lines.append("No errors found.")
        return "\n".join(lines)

    lines.append(f"Found {len(report.errors)} errors:")
    lines.extend(str(error) for error in report.errors)

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the LUT CSV files in the profile library.")
    parser.add_argument(
        "path",
        nargs="?",
        default=PROFILE_DIRECTORY,
        help="Profile library directory to validate.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = validate_library(Path(args.path))
    print(format_report(report))  # noqa: T201
    if report.has_errors:
        raise SystemExit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
