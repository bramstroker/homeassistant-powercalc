from __future__ import annotations

import csv
import gzip
from pathlib import Path

from utils.library.scan_lut_quality import (
    analyze_color_temp_lut,
    analyze_lut,
    find_lut_files,
    fix_lut_issues,
    format_text_report,
    read_lut,
    scan_library,
)

PROJECT_DIR = Path(__file__).parents[3]


def test_smooth_lut_scores_cleanly(tmp_path: Path) -> None:
    lut_path = tmp_path / "color_temp.csv"
    write_lut(
        lut_path,
        [
            (1, 150, 1.0),
            (1, 160, 1.2),
            (1, 170, 1.4),
            (1, 180, 1.6),
            (100, 150, 5.0),
            (100, 160, 5.2),
            (100, 170, 5.4),
            (100, 180, 5.6),
        ],
    )

    result = analyze_color_temp_lut(lut_path, root=tmp_path)

    assert result.path == "color_temp.csv"
    assert result.score == 100.0
    assert result.issues == []


def test_innr_rb_287_c_color_temp_scans_cleanly() -> None:
    lut_path = PROJECT_DIR / "profile_library/innr/RB 287 C/color_temp.csv.gz"

    result = analyze_color_temp_lut(lut_path, root=PROJECT_DIR / "profile_library")

    assert result.path == "innr/RB 287 C/color_temp.csv.gz"
    assert result.issues == []


def test_ikea_led2408g10_color_temp_scans_cleanly() -> None:
    lut_path = PROJECT_DIR / "profile_library/ikea/LED2408G10/color_temp.csv.gz"

    result = analyze_color_temp_lut(lut_path, root=PROJECT_DIR / "profile_library")

    assert result.path == "ikea/LED2408G10/color_temp.csv.gz"
    assert result.issues == []


def test_spiky_lut_reports_outlier(tmp_path: Path) -> None:
    lut_path = tmp_path / "color_temp.csv"
    write_lut(
        lut_path,
        [
            (64, 200, 2.0),
            (96, 200, 2.5),
            (128, 200, 8.5),
            (160, 200, 3.5),
            (192, 200, 4.0),
        ],
    )

    result = analyze_color_temp_lut(lut_path, root=tmp_path)

    assert result.score < 80
    assert len(result.issues) == 1
    assert result.issues[0].bri == 128
    assert result.issues[0].mired == 200
    assert result.issues[0].severity == "error"


def test_brightness_lut_reports_outlier(tmp_path: Path) -> None:
    lut_path = tmp_path / "brightness.csv"
    write_lut(
        lut_path,
        [
            (1, None, 1.0),
            (25, None, 2.0),
            (50, None, 8.0),
            (75, None, 4.0),
            (100, None, 5.0),
        ],
    )

    result = analyze_lut(lut_path, root=tmp_path)

    assert result.score < 80
    assert len(result.issues) == 1
    assert result.issues[0].mode == "brightness"
    assert result.issues[0].bri == 50
    assert result.issues[0].mired is None


def test_brightness_lut_filters_single_outlier_without_neighbor_cascade(tmp_path: Path) -> None:
    lut_path = tmp_path / "brightness.csv"
    write_lut(
        lut_path,
        [
            (203, None, 7.8),
            (204, None, 7.9),
            (205, None, 7.8),
            (206, None, 7.9),
            (207, None, 8.0),
            (208, None, 0.4),
            (209, None, 8.1),
            (210, None, 8.2),
            (211, None, 8.1),
            (212, None, 8.3),
        ],
    )

    result = analyze_lut(lut_path, root=tmp_path)

    assert [issue.bri for issue in result.issues] == [208]
    assert result.issues[0].expected_watt == 8.05


def test_brightness_lut_reports_two_low_points_in_alternating_psb30_case(tmp_path: Path) -> None:
    lut_path = tmp_path / "brightness.csv.gz"
    write_lut(
        lut_path,
        [
            (202, None, 7.9),
            (203, None, 7.8),
            (204, None, 7.9),
            (205, None, 7.8),
            (206, None, 7.9),
            (207, None, 4.15),
            (208, None, 8.05),
            (209, None, 4.3),
            (210, None, 8.2),
            (211, None, 8.1),
            (212, None, 8.3),
            (213, None, 8.2),
        ],
        gzipped=True,
    )

    result = analyze_lut(lut_path, root=tmp_path)

    assert sorted(issue.bri for issue in result.issues) == [207, 209]


def test_fix_lut_issues_removes_outlier_point(tmp_path: Path) -> None:
    lut_path = tmp_path / "brightness.csv"
    write_lut(
        lut_path,
        [
            (1, None, 1.0),
            (25, None, 2.0),
            (50, None, 8.0),
            (75, None, 4.0),
            (100, None, 5.0),
        ],
    )
    result = analyze_lut(lut_path, root=tmp_path)

    fix_result = fix_lut_issues(lut_path, result.issues, fix_mode="remove")

    assert fix_result.fixed_points == 1
    assert [(point.bri, point.watt) for point in read_lut(lut_path, "brightness")] == [
        (1, 1.0),
        (25, 2.0),
        (75, 4.0),
        (100, 5.0),
    ]
    assert analyze_lut(lut_path, root=tmp_path).issues == []


def test_fix_lut_issues_sets_outlier_to_expected_watt(tmp_path: Path) -> None:
    lut_path = tmp_path / "brightness.csv"
    write_lut(
        lut_path,
        [
            (1, None, 1.0),
            (25, None, 2.0),
            (50, None, 8.0),
            (75, None, 4.0),
            (100, None, 5.0),
        ],
    )
    result = analyze_lut(lut_path, root=tmp_path)

    fix_result = fix_lut_issues(lut_path, result.issues, fix_mode="expected")

    assert fix_result.fixed_points == 1
    assert [(point.bri, point.watt) for point in read_lut(lut_path, "brightness")] == [
        (1, 1.0),
        (25, 2.0),
        (50, 3.0),
        (75, 4.0),
        (100, 5.0),
    ]
    assert analyze_lut(lut_path, root=tmp_path).issues == []


def test_scan_library_finds_supported_gzipped_luts(tmp_path: Path) -> None:
    color_temp_path = tmp_path / "manufacturer" / "model" / "color_temp.csv.gz"
    brightness_path = tmp_path / "manufacturer" / "model" / "brightness.csv.gz"
    color_temp_path.parent.mkdir(parents=True)
    write_lut(
        color_temp_path,
        [
            (255, 150, 6.0),
            (255, 160, 6.1),
            (255, 170, 6.2),
        ],
        gzipped=True,
    )
    write_lut(
        brightness_path,
        [
            (1, None, 1.0),
            (128, None, 3.0),
            (255, None, 5.0),
        ],
        gzipped=True,
    )

    assert find_lut_files(tmp_path) == [brightness_path, color_temp_path]
    assert find_lut_files(tmp_path, mode="brightness") == [brightness_path]
    assert find_lut_files(tmp_path, mode="color_temp") == [color_temp_path]

    results = scan_library(tmp_path)

    assert [result.path for result in results] == [
        "manufacturer/model/brightness.csv.gz",
        "manufacturer/model/color_temp.csv.gz",
    ]

    brightness_results = scan_library(tmp_path, mode="brightness")

    assert [result.path for result in brightness_results] == ["manufacturer/model/brightness.csv.gz"]


def test_text_report_hides_clean_results_by_default(tmp_path: Path) -> None:
    lut_path = tmp_path / "color_temp.csv"
    write_lut(
        lut_path,
        [
            (1, 150, 1.0),
            (1, 160, 1.1),
            (1, 170, 1.2),
        ],
    )

    result = analyze_color_temp_lut(lut_path, root=tmp_path)

    assert format_text_report([result], show_ok=False, min_score=80.0) == "No LUT quality issues found."


def write_lut(path: Path, rows: list[tuple[int, int | None, float]], *, gzipped: bool = False) -> None:
    open_file = gzip.open if gzipped else Path.open
    with open_file(path, "wt", newline="") as lut_file:
        writer = csv.writer(lut_file)
        if path.name.startswith("brightness"):
            writer.writerow(["bri", "watt"])
            writer.writerows((bri, watt) for bri, _, watt in rows)
            return

        writer.writerow(["bri", "mired", "watt"])
        writer.writerows((bri, mired, watt) for bri, mired, watt in rows)
