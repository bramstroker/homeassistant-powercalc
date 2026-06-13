from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable, Sequence
import csv
from dataclasses import asdict, dataclass, replace
import gzip
import json
from pathlib import Path
import sys
from typing import TextIO

from utils.library.common import PROFILE_DIRECTORY

DEFAULT_MIN_SCORE = 80.0
DEFAULT_MAX_ABSOLUTE_DEVIATION = 0.75
DEFAULT_MAX_RELATIVE_DEVIATION = 0.12
DEFAULT_Z_SCORE = 6.0
SMOOTHING_MIN_POINTS = 8
SMOOTHING_WINDOW_RADIUS = 3
SUPPORTED_LUT_FILES = ("brightness.csv", "brightness.csv.gz", "color_temp.csv", "color_temp.csv.gz")
SUPPORTED_LUT_MODES = ("all", "brightness", "color_temp")
SCAN_LUT_MODES = ("brightness", "color_temp")
FIX_MODES = ("remove", "expected")
REPORT_SEVERITIES = ("all", "warning", "error")
MANUALLY_VERIFIED_MODELS = (
    "govee/H6076",
    "govee/H61B8",
    "govee/H7020",  # double check
    "ikea/LED2111G6",  # messy LUT, might need remeasurement
    "innr/RB 285 C",
    "innr/RS 229 T",  # multiple error points in the middle of the curve, might need remeasurement
    "kauf/BLF10",
    "ledvance/4058075208339",
    "lidl/HG07834A",
    "lidl/HG08131B",
    "lifx/LIFX A19 Night Vision",  # could be firmware bugs, there are outliers in lowest brightness levels
    "lifx/LIFX BR30 Night Vision",
    "lifx/LIFX Original 1000",
    "lifx/LIFX Downlight Color",
    "lifx/LIFX Candle",
    "osram/Classic A60 RGBW",
    "signify/1742930P7",
    "signify/5060730P7",
    "signify/5060830P7",
    "signify/LTW001",  # not really clean, could have remeasure
    "signify/LCG008",  # plots missing, check later
    "signify/LCT012",
    "signify/LTG005",  # very messy LUT, needs remeasure
    "signify/LTC001",
    "signify/LST002",
    "signify/LCT015",
    "signify/LCD002",
    "signify/929003598001",
    "signify/929003526101",  # messy LUT, bumpy, needs remeasure
    "signify/915005997801",
    "signify/1746230P7",
    "signify/1743730P7",
    "signify/1743530P7",
    "zipato/RGBWE2",
)


@dataclass(frozen=True)
class LutPoint:
    bri: int
    mired: int | None
    watt: float


@dataclass(frozen=True)
class LutQualityIssue:
    severity: str
    mode: str
    bri: int
    mired: int | None
    watt: float
    expected_watt: float
    deviation: float
    threshold: float
    message: str


@dataclass(frozen=True)
class LutQualityResult:
    path: str
    score: float
    rows: int
    brightness_curves: int
    max_deviation: float
    mean_deviation: float
    issues: list[LutQualityIssue]

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


@dataclass(frozen=True)
class LutFixResult:
    path: str
    fixed_points: int


@dataclass(frozen=True)
class CurveDeviation:
    index: int
    point: LutPoint
    expected_watt: float
    deviation: float


def scan_library(
    root: Path,
    *,
    mode: str = "all",
    max_absolute_deviation: float = DEFAULT_MAX_ABSOLUTE_DEVIATION,
    max_relative_deviation: float = DEFAULT_MAX_RELATIVE_DEVIATION,
    z_score: float = DEFAULT_Z_SCORE,
) -> list[LutQualityResult]:
    """Scan all supported LUT files below root."""
    return [
        analyze_lut(
            path,
            root=root,
            max_absolute_deviation=max_absolute_deviation,
            max_relative_deviation=max_relative_deviation,
            z_score=z_score,
        )
        for path in find_lut_files(root, mode=mode)
    ]


def find_lut_files(root: Path, *, mode: str = "all") -> list[Path]:
    """Return all supported LUT CSV files below root."""
    if mode != "all":
        validate_lut_mode(mode)

    paths = [
        path
        for file_name in SUPPORTED_LUT_FILES
        for path in root.rglob(file_name)
        if not is_manually_verified_model_path(path, root)
    ]
    if mode != "all":
        paths = [path for path in paths if get_lut_mode(path) == mode]

    return sorted(paths, key=lambda path: path.as_posix())


def is_manually_verified_model_path(path: Path, root: Path) -> bool:
    if not path.is_relative_to(root):
        return False

    relative_parent = path.parent.relative_to(root).as_posix()
    return any(
        relative_parent == model_path or relative_parent.startswith(f"{model_path}/")
        for model_path in MANUALLY_VERIFIED_MODELS
    )


def find_color_temp_lut_files(root: Path) -> list[Path]:
    """Return all color_temp LUT CSV files below root."""
    return [path for path in find_lut_files(root) if get_lut_mode(path) == "color_temp"]


def analyze_color_temp_lut(
    path: Path,
    *,
    root: Path | None = None,
    max_absolute_deviation: float = DEFAULT_MAX_ABSOLUTE_DEVIATION,
    max_relative_deviation: float = DEFAULT_MAX_RELATIVE_DEVIATION,
    z_score: float = DEFAULT_Z_SCORE,
) -> LutQualityResult:
    """Score a color_temp LUT file by looking for non-smooth points in each mired curve."""
    return analyze_lut(
        path,
        root=root,
        max_absolute_deviation=max_absolute_deviation,
        max_relative_deviation=max_relative_deviation,
        z_score=z_score,
    )


def analyze_lut(
    path: Path,
    *,
    root: Path | None = None,
    max_absolute_deviation: float = DEFAULT_MAX_ABSOLUTE_DEVIATION,
    max_relative_deviation: float = DEFAULT_MAX_RELATIVE_DEVIATION,
    z_score: float = DEFAULT_Z_SCORE,
) -> LutQualityResult:
    """Score a LUT file by looking for non-smooth points."""
    mode = get_lut_mode(path)
    points = read_lut(path, mode)
    curves = group_points(points, mode)
    issues: list[LutQualityIssue] = []
    deviations: list[float] = []

    for curve_key, curve in curves.items():
        curve_issues, curve_deviations = analyze_brightness_curve(
            mode,
            curve_key,
            curve,
            max_absolute_deviation=max_absolute_deviation,
            max_relative_deviation=max_relative_deviation,
            z_score=z_score,
        )
        issues.extend(curve_issues)
        deviations.extend(curve_deviations)

    max_deviation = max(deviations, default=0.0)
    mean_deviation = sum(deviations) / len(deviations) if deviations else 0.0
    score = calculate_score(issues, max_deviation, mean_deviation, points)
    display_path = path.relative_to(root).as_posix() if root and path.is_relative_to(root) else path.as_posix()

    return LutQualityResult(
        path=display_path,
        score=score,
        rows=len(points),
        brightness_curves=len(curves),
        max_deviation=round(max_deviation, 3),
        mean_deviation=round(mean_deviation, 3),
        issues=sorted(issues, key=lambda issue: (-issue.deviation, issue.bri, issue.mired)),
    )


def get_lut_mode(path: Path) -> str:
    file_name = path.name.removesuffix(".gz").removesuffix(".csv")
    if file_name not in SCAN_LUT_MODES:
        raise ValueError(f"Unsupported LUT file: {path}")
    return file_name


def validate_lut_mode(mode: str) -> None:
    if mode not in SUPPORTED_LUT_MODES:
        supported_modes = ", ".join(SUPPORTED_LUT_MODES)
        raise ValueError(f"Unsupported LUT mode: {mode}. Expected one of: {supported_modes}")


def read_lut(path: Path, mode: str) -> list[LutPoint]:
    """Read a LUT from plain or gzipped CSV."""
    with open_lut_file(path) as lut_file:
        reader = csv.DictReader(lut_file)
        required_headers = {"bri", "watt"} if mode == "brightness" else {"bri", "mired", "watt"}
        missing_headers = required_headers - set(reader.fieldnames or [])
        if missing_headers:
            missing = ", ".join(sorted(missing_headers))
            raise ValueError(f"{path}: missing required columns: {missing}")

        return [
            LutPoint(
                bri=int(row["bri"]),
                mired=int(row["mired"]) if mode == "color_temp" else None,
                watt=float(row["watt"]),
            )
            for row in reader
        ]


def open_lut_file(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt")

    return path.open()


def write_lut(path: Path, fieldnames: Sequence[str], rows: Sequence[dict[str, str]]) -> None:
    with open_lut_file_for_write(path) as lut_file:
        writer = csv.DictWriter(lut_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def open_lut_file_for_write(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "wt", newline="")

    return path.open("w", newline="")


def fix_lut_issues(path: Path, issues: Sequence[LutQualityIssue], *, fix_mode: str) -> LutFixResult:
    if fix_mode not in FIX_MODES:
        supported_modes = ", ".join(FIX_MODES)
        raise ValueError(f"Unsupported fix mode: {fix_mode}. Expected one of: {supported_modes}")

    if not issues:
        return LutFixResult(path=path.as_posix(), fixed_points=0)

    lut_mode = get_lut_mode(path)
    with open_lut_file(path) as lut_file:
        reader = csv.DictReader(lut_file)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"{path}: missing CSV header")
        rows = list(reader)

    issue_lookup = {(issue.bri, issue.mired): issue for issue in issues}
    fixed_points = 0
    fixed_rows: list[dict[str, str]] = []

    for row in rows:
        key = get_row_issue_key(row, lut_mode)
        issue = issue_lookup.get(key)
        if issue is None:
            fixed_rows.append(row)
            continue

        fixed_points += 1
        if fix_mode == "expected":
            row["watt"] = format_fixed_watt(issue.expected_watt)
            fixed_rows.append(row)

    write_lut(path, fieldnames, fixed_rows)
    return LutFixResult(path=path.as_posix(), fixed_points=fixed_points)


def get_row_issue_key(row: dict[str, str], mode: str) -> tuple[int, int | None]:
    return int(row["bri"]), int(row["mired"]) if mode == "color_temp" else None


def format_fixed_watt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def group_points(points: Iterable[LutPoint], mode: str) -> dict[int, list[LutPoint]]:
    if mode == "brightness":
        return {0: sorted(points, key=lambda point: point.bri)}

    curves: dict[int, list[LutPoint]] = defaultdict(list)
    for point in points:
        if point.mired is None:
            raise ValueError("Cannot group color_temp curve without mired values")
        curves[point.mired].append(point)

    return {mired: sorted(curve, key=lambda point: point.bri) for mired, curve in sorted(curves.items())}


def analyze_brightness_curve(
    mode: str,
    curve_key: int,
    curve: Sequence[LutPoint],
    *,
    max_absolute_deviation: float,
    max_relative_deviation: float,
    z_score: float,
) -> tuple[list[LutQualityIssue], list[float]]:
    """Find points that deviate from a robust local smooth curve."""
    if len(curve) < 3:
        return [], []

    candidate_deviations = calculate_detection_curve_deviations(mode, curve)
    deviations = [candidate.deviation for candidate in candidate_deviations]
    curve_range = max(point.watt for point in curve) - min(point.watt for point in curve)
    threshold = calculate_curve_threshold(
        deviations,
        curve_range=curve_range,
        max_absolute_deviation=max_absolute_deviation,
        max_relative_deviation=max_relative_deviation,
        z_score=z_score,
    )

    issues = detect_curve_issues(mode, curve_key, curve, candidate_deviations, threshold)
    return issues, deviations


def detect_curve_issues(
    mode: str,
    curve_key: int,
    curve: Sequence[LutPoint],
    candidate_deviations: Sequence[CurveDeviation],
    threshold: float,
) -> list[LutQualityIssue]:
    candidates = [candidate for candidate in candidate_deviations if candidate.deviation > threshold]
    clusters = group_adjacent_deviations(candidates)
    selected_candidates = [
        max(
            cluster,
            key=lambda candidate: (
                calculate_correction_improvement(mode, curve, candidate, threshold),
                candidate.deviation,
            ),
        )
        for cluster in clusters
    ]

    return [
        create_issue(
            mode,
            curve_key,
            curve[selected.index],
            selected.expected_watt,
            selected.deviation,
            threshold,
        )
        for selected in selected_candidates
    ]


def group_adjacent_deviations(candidates: Sequence[CurveDeviation]) -> list[list[CurveDeviation]]:
    clusters: list[list[CurveDeviation]] = []
    for candidate in candidates:
        if not clusters or candidate.index != clusters[-1][-1].index + 1:
            clusters.append([candidate])
            continue

        clusters[-1].append(candidate)

    return clusters


def calculate_curve_deviations(curve: Sequence[LutPoint]) -> list[CurveDeviation]:
    return [calculate_curve_deviation(curve, index) for index in range(1, len(curve) - 1)]


def calculate_detection_curve_deviations(mode: str, curve: Sequence[LutPoint]) -> list[CurveDeviation]:
    if mode == "color_temp":
        return calculate_color_temp_curve_deviations(curve)

    if len(curve) < SMOOTHING_MIN_POINTS:
        return calculate_curve_deviations(curve)

    return calculate_smoothed_curve_deviations(curve)


def calculate_color_temp_curve_deviations(curve: Sequence[LutPoint]) -> list[CurveDeviation]:
    return [calculate_color_temp_curve_deviation(curve, index) for index in range(1, len(curve) - 1)]


def calculate_color_temp_curve_deviation(curve: Sequence[LutPoint], index: int) -> CurveDeviation:
    point = curve[index]
    expected_watt = calculate_color_temp_expected_watt(curve, index)
    return CurveDeviation(
        index=index,
        point=point,
        expected_watt=expected_watt,
        deviation=abs(point.watt - expected_watt),
    )


def calculate_color_temp_expected_watt(curve: Sequence[LutPoint], index: int) -> float:
    if index == 1 and len(curve) >= SMOOTHING_MIN_POINTS:
        return interpolate_watt(curve[2], curve[3], get_axis_value(curve[index]))

    return interpolate_watt(curve[index - 1], curve[index + 1], get_axis_value(curve[index]))


def calculate_smoothed_curve_deviations(curve: Sequence[LutPoint]) -> list[CurveDeviation]:
    return [calculate_smoothed_curve_deviation(curve, index) for index in range(1, len(curve) - 1)]


def calculate_correction_improvement(
    mode: str,
    curve: Sequence[LutPoint],
    candidate: CurveDeviation,
    threshold: float,
) -> float:
    before = calculate_total_excess_deviation(mode, curve, threshold)
    corrected_curve = list(curve)
    corrected_curve[candidate.index] = LutPoint(
        bri=candidate.point.bri,
        mired=candidate.point.mired,
        watt=candidate.expected_watt,
    )
    after = calculate_total_excess_deviation(mode, corrected_curve, threshold)
    return before - after


def calculate_total_excess_deviation(mode: str, curve: Sequence[LutPoint], threshold: float) -> float:
    return sum(
        max(candidate.deviation - threshold, 0.0) for candidate in calculate_detection_curve_deviations(mode, curve)
    )


def calculate_curve_deviation(curve: Sequence[LutPoint], index: int) -> CurveDeviation:
    point = curve[index]
    expected_watt = interpolate_watt(curve[index - 1], curve[index + 1], get_axis_value(point))
    return CurveDeviation(
        index=index,
        point=point,
        expected_watt=expected_watt,
        deviation=abs(point.watt - expected_watt),
    )


def calculate_smoothed_curve_deviation(curve: Sequence[LutPoint], index: int) -> CurveDeviation:
    point = curve[index]
    expected_watt = calculate_smoothed_expected_watt(curve, index)
    return CurveDeviation(
        index=index,
        point=point,
        expected_watt=expected_watt,
        deviation=abs(point.watt - expected_watt),
    )


def calculate_smoothed_expected_watt(curve: Sequence[LutPoint], index: int) -> float:
    start = max(0, index - SMOOTHING_WINDOW_RADIUS)
    end = min(len(curve), index + SMOOTHING_WINDOW_RADIUS + 1)
    neighbor_watts = [
        point.watt for neighbor_index, point in enumerate(curve[start:end], start=start) if neighbor_index != index
    ]
    if len(neighbor_watts) < 2:
        return interpolate_watt(curve[index - 1], curve[index + 1], get_axis_value(curve[index]))

    return median(neighbor_watts)


def calculate_point_deviation(curve: Sequence[LutPoint], index: int) -> tuple[LutPoint, float]:
    deviation = calculate_curve_deviation(curve, index)
    return deviation.point, deviation.deviation


def expected_values(curve: Sequence[LutPoint]) -> list[float]:
    return [
        interpolate_watt(curve[index - 1], curve[index + 1], get_axis_value(curve[index]))
        for index in range(1, len(curve) - 1)
    ]


def get_axis_value(point: LutPoint) -> int:
    return point.mired if point.mired is not None else point.bri


def interpolate_watt(left: LutPoint, right: LutPoint, axis_value: int) -> float:
    left_axis = get_axis_value(left)
    right_axis = get_axis_value(right)
    if left_axis == right_axis:
        return (left.watt + right.watt) / 2

    ratio = (axis_value - left_axis) / (right_axis - left_axis)
    return left.watt + ((right.watt - left.watt) * ratio)


def calculate_curve_threshold(
    deviations: Sequence[float],
    *,
    curve_range: float,
    max_absolute_deviation: float,
    max_relative_deviation: float,
    z_score: float,
) -> float:
    if not deviations:
        return max_absolute_deviation

    median_deviation = median(deviations)
    mad = median([abs(deviation - median_deviation) for deviation in deviations])
    robust_threshold = median_deviation + (z_score * 1.4826 * mad)
    relative_threshold = curve_range * max_relative_deviation
    return max(max_absolute_deviation, relative_threshold, robust_threshold)


def create_issue(
    mode: str,
    _curve_key: int,
    point: LutPoint,
    expected_watt: float,
    deviation: float,
    threshold: float,
) -> LutQualityIssue:
    severity = "error" if deviation > threshold * 1.5 else "warning"
    location = f"brightness {point.bri}, mired {point.mired}" if mode == "color_temp" else f"brightness {point.bri}"
    return LutQualityIssue(
        severity=severity,
        mode=mode,
        bri=point.bri,
        mired=point.mired,
        watt=round(point.watt, 3),
        expected_watt=round(expected_watt, 3),
        deviation=round(deviation, 3),
        threshold=round(threshold, 3),
        message=f"{location}: {point.watt:.3f} W deviates {deviation:.3f} W from smooth curve",
    )


def calculate_score(
    issues: Sequence[LutQualityIssue],
    max_deviation: float,
    mean_deviation: float,
    points: Sequence[LutPoint],
) -> float:
    """Calculate a 0-100 score where 100 is a perfectly smooth LUT."""
    if not points:
        return 0.0

    watt_range = max(point.watt for point in points) - min(point.watt for point in points)
    normalized_max = max_deviation / max(watt_range, 1.0)
    normalized_mean = mean_deviation / max(watt_range, 1.0)
    issue_penalty = min(60.0, len(issues) * 8.0)
    deviation_penalty = min(25.0, normalized_max * 35.0)
    roughness_penalty = min(15.0, normalized_mean * 60.0)
    return round(max(0.0, 100.0 - issue_penalty - deviation_penalty - roughness_penalty), 1)


def median(values: Sequence[float]) -> float:
    if not values:
        return 0.0

    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[midpoint]

    return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2


def format_text_report(results: Sequence[LutQualityResult], *, show_ok: bool, min_score: float) -> str:
    lines: list[str] = []
    for result in results:
        if not show_ok and result.score >= min_score and not result.has_issues:
            continue

        summary_parts = [
            f"{result.path}: score={result.score:.1f}",
            f"rows={result.rows}",
            f"curves={result.brightness_curves}",
            f"issues={len(result.issues)}",
            f"max_deviation={result.max_deviation:.3f}W",
        ]
        lines.append(" ".join(summary_parts))
        lines.extend(
            f"  {issue.severity}: {issue.message} (expected {issue.expected_watt:.3f} W)" for issue in result.issues[:5]
        )
        if len(result.issues) > 5:
            lines.append(f"  ... {len(result.issues) - 5} more issues")

    if lines:
        return "\n".join(lines)

    return "No LUT quality issues found."


def format_json_report(results: Sequence[LutQualityResult]) -> str:
    return json.dumps([asdict(result) for result in results], indent=2)


def filter_results_by_severity(results: Sequence[LutQualityResult], severity: str) -> list[LutQualityResult]:
    if severity not in REPORT_SEVERITIES:
        supported_severities = ", ".join(REPORT_SEVERITIES)
        raise ValueError(f"Unsupported report severity: {severity}. Expected one of: {supported_severities}")

    if severity == "all":
        return list(results)

    return [
        replace(
            result,
            issues=[issue for issue in result.issues if issue.severity == severity],
        )
        for result in results
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan profile library LUT files for rough curves and outliers.")
    parser.add_argument(
        "path",
        nargs="?",
        default=PROFILE_DIRECTORY,
        help="Profile library directory or a single brightness/color_temp CSV file.",
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_LUT_MODES,
        default="all",
        help="Only scan LUT files for a specific color mode.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Report output format.")
    parser.add_argument(
        "--severity",
        choices=REPORT_SEVERITIES,
        default="all",
        help="Only include issues with this severity in the report.",
    )
    parser.add_argument("--show-ok", action="store_true", help="Show LUT files without issues.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_MIN_SCORE,
        help="Score used for filtering text output.",
    )
    parser.add_argument("--fail-under", type=float, help="Exit with status 1 when any LUT scores below this value.")
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Exit with status 1 when any reported issues remain.",
    )
    parser.add_argument(
        "--fix",
        choices=FIX_MODES,
        help="Automatically fix detected points by removing them or setting watt to the expected value.",
    )
    parser.add_argument(
        "--max-absolute-deviation",
        type=float,
        default=DEFAULT_MAX_ABSOLUTE_DEVIATION,
        help="Minimum allowed deviation in watts.",
    )
    parser.add_argument(
        "--max-relative-deviation",
        type=float,
        default=DEFAULT_MAX_RELATIVE_DEVIATION,
        help="Allowed deviation as a fraction of the curve watt range.",
    )
    parser.add_argument(
        "--z-score",
        type=float,
        default=DEFAULT_Z_SCORE,
        help="Robust MAD multiplier used for adaptive thresholds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target = Path(args.path)
    if target.is_file():
        root = target.parent
        results = [
            analyze_lut(
                target,
                root=root,
                max_absolute_deviation=args.max_absolute_deviation,
                max_relative_deviation=args.max_relative_deviation,
                z_score=args.z_score,
            ),
        ]
    else:
        root = target
        results = scan_library(
            root,
            mode=args.mode,
            max_absolute_deviation=args.max_absolute_deviation,
            max_relative_deviation=args.max_relative_deviation,
            z_score=args.z_score,
        )

    if args.fix:
        fixed_results = [
            fix_lut_issues(root / result.path, result.issues, fix_mode=args.fix)
            for result in results
            if result.has_issues
        ]
        fixed_points = sum(result.fixed_points for result in fixed_results)
        if fixed_points:
            print(f"Fixed {fixed_points} LUT point(s).", file=sys.stderr)  # noqa: T201
            if target.is_file():
                results = [
                    analyze_lut(
                        target,
                        root=root,
                        max_absolute_deviation=args.max_absolute_deviation,
                        max_relative_deviation=args.max_relative_deviation,
                        z_score=args.z_score,
                    ),
                ]
            else:
                results = scan_library(
                    root,
                    mode=args.mode,
                    max_absolute_deviation=args.max_absolute_deviation,
                    max_relative_deviation=args.max_relative_deviation,
                    z_score=args.z_score,
                )

    report_results = filter_results_by_severity(results, args.severity)
    report_min_score = 0.0 if args.severity != "all" else args.min_score
    report = (
        format_json_report(report_results)
        if args.format == "json"
        else format_text_report(report_results, show_ok=args.show_ok, min_score=report_min_score)
    )
    print(report)  # noqa: T201

    if args.fail_under is not None and any(result.score < args.fail_under for result in results):
        raise SystemExit(1)

    if args.fail_on_issues and any(result.has_issues for result in report_results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
