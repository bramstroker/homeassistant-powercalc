from __future__ import annotations

from collections.abc import Callable
import csv
import gzip
from pathlib import Path
from typing import TextIO

import pytest

from utils.library.validate_lut_files import (
    BRI_RULE,
    EFFECT_RULE,
    MAX_ERRORS_PER_FILE,
    WATT_RULE,
    ColumnRule,
    LutValidationError,
    ValidationReport,
    find_lut_files,
    find_profile_directories,
    format_report,
    get_color_mode,
    main,
    parse_int,
    validate_color_modes,
    validate_library,
    validate_lut_file,
    validate_max_brightness,
    validate_profile,
    validate_row,
)

BRIGHTNESS_ROWS = [(1, 0.4), (128, 5.2), (255, 9.8)]


def write_lut(path: Path, header: list[str], rows: list[tuple[object, ...]]) -> None:
    with open_for_write(path) as lut_file:
        writer = csv.writer(lut_file)
        writer.writerow(header)
        writer.writerows(rows)


def open_for_write(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "wt", newline="")

    return path.open("w", newline="")


def write_brightness_lut(path: Path, rows: list[tuple[int, float]] | None = None) -> Path:
    write_lut(path, ["bri", "watt"], list(rows if rows is not None else BRIGHTNESS_ROWS))
    return path


def write_color_temp_lut(path: Path) -> Path:
    write_lut(path, ["bri", "mired", "watt"], [(1, 153, 0.4), (255, 500, 9.8)])
    return path


def write_hs_lut(path: Path) -> Path:
    write_lut(path, ["bri", "hue", "sat", "watt"], [(1, 0, 0, 0.4), (255, 65535, 254, 9.8)])
    return path


def write_effect_lut(path: Path) -> Path:
    write_lut(path, ["effect", "bri", "watt"], [("none", 1, 0.4), ("candle", 255, 9.8)])
    return path


def test_column_rule_accepts_valid_values() -> None:
    assert BRI_RULE.validate("128") is None
    assert WATT_RULE.validate("9.8") is None
    assert EFFECT_RULE.validate("candle") is None


def test_column_rule_rejects_empty_string_value() -> None:
    assert EFFECT_RULE.validate("") == "'effect' is empty"


def test_column_rule_rejects_non_numeric_values() -> None:
    assert BRI_RULE.validate("high") == "'bri' value 'high' is not a valid integer"
    assert WATT_RULE.validate("many") == "'watt' value 'many' is not a valid number"


def test_column_rule_rejects_values_out_of_range() -> None:
    assert BRI_RULE.validate("-1") == "'bri' value -1 is less than minimum 0"
    assert BRI_RULE.validate("256") == "'bri' value 256 is greater than maximum 255"


def test_column_rule_without_bounds_accepts_any_number() -> None:
    rule = ColumnRule("watt", "number")

    assert rule.validate("-12.5") is None


@pytest.mark.parametrize(
    "file_name,expected",
    [
        ("brightness.csv.gz", "brightness"),
        ("color_temp.csv.gz", "color_temp"),
        ("hs.csv", "hs"),
        ("effect.csv", "effect"),
        ("tapering.csv.gz", None),
        ("model.json", None),
    ],
)
def test_get_color_mode(file_name: str, expected: str | None) -> None:
    assert get_color_mode(Path("signify") / "LCT010" / file_name) == expected


def test_find_profile_directories_returns_directories_holding_lut_files(tmp_path: Path) -> None:
    model = tmp_path / "signify" / "LCT010"
    sub_profile = model / "length_2m"
    sub_profile.mkdir(parents=True)
    write_brightness_lut(model / "brightness.csv.gz")
    write_color_temp_lut(sub_profile / "color_temp.csv")
    (tmp_path / "signify" / "manufacturer.json").write_text("{}")
    (model / "tapering.csv.gz").write_bytes(gzip.compress(b"bri,watt\n"))

    assert find_profile_directories(tmp_path) == [model, sub_profile]


def test_find_lut_files_only_returns_files_in_the_directory_itself(tmp_path: Path) -> None:
    sub_profile = tmp_path / "length_2m"
    sub_profile.mkdir()
    write_color_temp_lut(sub_profile / "color_temp.csv.gz")
    write_hs_lut(tmp_path / "hs.csv.gz")
    write_brightness_lut(tmp_path / "brightness.csv.gz")
    (tmp_path / "model.json").write_text("{}")

    assert find_lut_files(tmp_path) == [
        (tmp_path / "brightness.csv.gz", "brightness"),
        (tmp_path / "hs.csv.gz", "hs"),
    ]


@pytest.mark.parametrize(
    "color_mode,writer",
    [
        ("brightness", write_brightness_lut),
        ("color_temp", write_color_temp_lut),
        ("hs", write_hs_lut),
        ("effect", write_effect_lut),
    ],
)
def test_valid_lut_file_has_no_errors(tmp_path: Path, color_mode: str, writer: Callable[[Path], Path]) -> None:
    path = writer(tmp_path / f"{color_mode}.csv.gz")

    assert validate_lut_file(path, color_mode) == []


def test_lut_file_with_bom_is_read_correctly(tmp_path: Path) -> None:
    path = tmp_path / "effect.csv.gz"
    path.write_bytes(gzip.compress("﻿effect,bri,watt\nnone,255,9.8\n".encode()))

    assert validate_lut_file(path, "effect") == []


def test_plain_csv_lut_file_is_validated(tmp_path: Path) -> None:
    path = write_brightness_lut(tmp_path / "brightness.csv")

    assert validate_lut_file(path, "brightness") == []


def test_missing_columns_are_reported_once(tmp_path: Path) -> None:
    path = tmp_path / "hs.csv.gz"
    write_lut(path, ["bri", "watt"], [(255, 9.8)])

    assert validate_lut_file(path, "hs") == ["missing required columns: hue, sat"]


def test_empty_file_is_reported_as_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "brightness.csv.gz"
    path.write_bytes(gzip.compress(b""))

    assert validate_lut_file(path, "brightness") == ["missing required columns: bri, watt"]


def test_file_without_data_rows_is_reported(tmp_path: Path) -> None:
    path = write_brightness_lut(tmp_path / "brightness.csv.gz", [])

    assert validate_lut_file(path, "brightness") == ["file contains no data rows"]


def test_row_errors_are_prefixed_with_the_line_number(tmp_path: Path) -> None:
    path = tmp_path / "color_temp.csv.gz"
    write_lut(path, ["bri", "mired", "watt"], [(255, 153, 9.8), (300, 1200, 0.0)])

    assert validate_lut_file(path, "color_temp") == [
        "row 3: 'bri' value 300 is greater than maximum 255",
        "row 3: 'mired' value 1200 is greater than maximum 1000",
        "row 3: 'watt' value 0.0 is less than minimum 0.01",
    ]


def test_short_row_reports_the_missing_value(tmp_path: Path) -> None:
    path = tmp_path / "hs.csv.gz"
    path.write_bytes(gzip.compress(b"bri,hue,sat,watt\n255,100,50\n"))

    assert validate_lut_file(path, "hs") == ["row 2: 'watt' is missing"]


def test_row_errors_are_truncated(tmp_path: Path) -> None:
    path = tmp_path / "brightness.csv.gz"
    write_lut(path, ["bri", "watt"], [(255, 9.8), *((256, 9.8) for _ in range(MAX_ERRORS_PER_FILE + 3))])

    errors = validate_lut_file(path, "brightness")

    assert len(errors) == MAX_ERRORS_PER_FILE + 1
    assert errors[-1] == "... and 3 more row errors"


def test_unfinished_measurement_is_reported(tmp_path: Path) -> None:
    path = write_brightness_lut(tmp_path / "brightness.csv.gz", [(1, 0.4), (249, 5.2)])

    assert validate_lut_file(path, "brightness") == [
        "max brightness level 249 is less than 250, measurements probably not finished completely",
    ]


def test_max_brightness_ignores_unparsable_brightness_values() -> None:
    assert validate_max_brightness([]) == ["file contains no data rows"]
    assert validate_max_brightness([255]) == []


def test_validate_row_reports_every_offending_column() -> None:
    assert validate_row({"bri": "256", "watt": "0"}, (BRI_RULE, WATT_RULE)) == [
        "'bri' value 256 is greater than maximum 255",
        "'watt' value 0.0 is less than minimum 0.01",
    ]


@pytest.mark.parametrize(
    "color_modes",
    [
        ["brightness"],
        ["color_temp"],
        ["hs"],
        ["color_temp", "hs"],
        ["brightness", "hs"],
        ["brightness", "color_temp"],
        ["brightness", "color_temp", "hs"],
        ["color_temp", "effect", "hs"],
        ["effect"],
        [],
    ],
)
def test_valid_color_mode_combinations(color_modes: list[str]) -> None:
    assert validate_color_modes(color_modes) is None


def test_invalid_color_mode_combination() -> None:
    assert validate_color_modes(["hs", "brightness", "color_temp", "unknown"]) == (
        "invalid color mode combination brightness,color_temp,hs,unknown"
    )


def test_validate_profile_reports_color_mode_combination(tmp_path: Path) -> None:
    model = tmp_path / "signify" / "LCT010"
    model.mkdir(parents=True)
    write_brightness_lut(model / "brightness.csv.gz")
    write_color_temp_lut(model / "color_temp.csv.gz")
    write_lut(model / "hs.csv.gz", ["bri", "hue", "sat", "watt"], [(255, 70000, 0, 9.8)])

    files, errors = validate_profile(model, tmp_path)

    assert files == 3
    assert errors == [
        LutValidationError(
            profile="signify/LCT010",
            message="row 2: 'hue' value 70000 is greater than maximum 65535",
            color_mode="hs",
        ),
    ]


def test_validate_library_walks_every_profile(tmp_path: Path) -> None:
    model = tmp_path / "signify" / "LCT010"
    sub_profile = model / "length_2m"
    sub_profile.mkdir(parents=True)
    write_color_temp_lut(model / "color_temp.csv.gz")
    write_hs_lut(model / "hs.csv.gz")
    write_brightness_lut(sub_profile / "brightness.csv.gz")
    write_hs_lut(sub_profile / "hs.csv.gz")
    write_effect_lut(sub_profile / "effect.csv.gz")

    report = validate_library(tmp_path)

    assert report == ValidationReport(profiles=2, files=5, errors=[])
    assert not report.has_errors


def test_validate_library_ignores_files_that_are_not_luts(tmp_path: Path) -> None:
    model = tmp_path / "signify" / "LCT010"
    model.mkdir(parents=True)
    write_lut(model / "tapering.csv.gz", ["bri", "watt"], [(1, 9.8)])
    (model / "hs.csv.gz").write_bytes(gzip.compress(b"bri,hue,sat,watt\n"))

    report = validate_library(tmp_path)

    assert report == ValidationReport(
        profiles=1,
        files=1,
        errors=[LutValidationError(profile="signify/LCT010", message="file contains no data rows", color_mode="hs")],
    )


def test_validate_profile_reports_an_unsupported_color_mode_combination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("utils.library.validate_lut_files.VALID_COLOR_MODE_COMBINATIONS", (frozenset({"hs"}),))
    model = tmp_path / "signify" / "LCT010"
    model.mkdir(parents=True)
    write_brightness_lut(model / "brightness.csv.gz")
    write_effect_lut(model / "effect.csv.gz")

    _, errors = validate_profile(model, tmp_path)

    assert errors == [
        LutValidationError(profile="signify/LCT010", message="invalid color mode combination brightness"),
    ]


def test_parse_int() -> None:
    assert parse_int("42") == 42
    assert parse_int("nope") is None
    assert parse_int(None) is None


def test_format_report_without_errors() -> None:
    assert format_report(ValidationReport(profiles=2, files=5)) == (
        "Validated 5 LUT files in 2 profiles.\nNo errors found."
    )


def test_format_report_with_errors() -> None:
    report = ValidationReport(
        profiles=1,
        files=1,
        errors=[
            LutValidationError(profile="signify/LCT010", message="row 2: 'bri' is missing", color_mode="hs"),
            LutValidationError(profile="signify/LCT010", message="invalid color mode combination hs,unknown"),
        ],
    )

    assert format_report(report) == (
        "Validated 1 LUT files in 1 profiles.\n"
        "Found 2 errors:\n"
        "signify/LCT010 - hs: row 2: 'bri' is missing\n"
        "signify/LCT010: invalid color mode combination hs,unknown"
    )


def test_main_succeeds_for_a_valid_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = tmp_path / "signify" / "LCT010"
    model.mkdir(parents=True)
    write_brightness_lut(model / "brightness.csv.gz")
    monkeypatch.setattr("sys.argv", ["validate_lut_files", str(tmp_path)])

    main()

    assert capsys.readouterr().out == "Validated 1 LUT files in 1 profiles.\nNo errors found.\n"


def test_main_exits_with_an_error_for_an_invalid_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = tmp_path / "signify" / "LCT010"
    model.mkdir(parents=True)
    write_brightness_lut(model / "brightness.csv.gz", [(1, 0.4)])
    monkeypatch.setattr("sys.argv", ["validate_lut_files", str(tmp_path)])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert "Found 1 errors:" in capsys.readouterr().out


def test_main_defaults_to_the_profile_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_brightness_lut(tmp_path / "brightness.csv.gz")
    monkeypatch.setattr("utils.library.validate_lut_files.PROFILE_DIRECTORY", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["validate_lut_files"])

    main()

    assert "Validated 1 LUT files" in capsys.readouterr().out
