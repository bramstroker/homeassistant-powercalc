from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import gzip
from pathlib import Path
from typing import TextIO

from utils.library.common import PROFILE_DIRECTORY

CSV_PATTERNS = ("*.csv", "*.csv.gz")
SORT_MODES = ("path", "rows")


@dataclass(frozen=True)
class CsvRowCount:
    path: str
    rows: int


def scan_library(root: Path) -> list[CsvRowCount]:
    """Count the data rows of every CSV file below root."""
    return [count_csv_rows(path, root=root) for path in find_csv_files(root)]


def find_csv_files(root: Path) -> list[Path]:
    """Return all plain and gzipped CSV files below root."""
    paths = [path for pattern in CSV_PATTERNS for path in root.rglob(pattern)]
    return sorted(paths, key=lambda path: path.as_posix())


def count_csv_rows(path: Path, *, root: Path | None = None) -> CsvRowCount:
    """Count the data rows (excluding the header) in a plain or gzipped CSV file."""
    with open_csv_file(path) as csv_file:
        reader = csv.reader(csv_file)
        next(reader, None)  # header
        rows = sum(1 for _ in reader)

    display_path = path.relative_to(root).as_posix() if root and path.is_relative_to(root) else path.as_posix()
    return CsvRowCount(path=display_path, rows=rows)


def open_csv_file(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt")

    return path.open()


def sort_results(results: list[CsvRowCount], sort: str) -> list[CsvRowCount]:
    if sort not in SORT_MODES:
        supported_modes = ", ".join(SORT_MODES)
        raise ValueError(f"Unsupported sort mode: {sort}. Expected one of: {supported_modes}")

    if sort == "rows":
        return sorted(results, key=lambda result: (-result.rows, result.path))

    return sorted(results, key=lambda result: result.path)


def format_report(results: list[CsvRowCount]) -> str:
    lines = [f"{result.path}: {result.rows}" for result in results]
    total_rows = sum(result.rows for result in results)
    lines.append(f"Total: {total_rows} rows in {len(results)} CSV file(s)")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List the number of data points (rows) per CSV file in the library.")
    parser.add_argument(
        "path",
        nargs="?",
        default=PROFILE_DIRECTORY,
        help="Profile library directory to scan.",
    )
    parser.add_argument(
        "--sort",
        choices=SORT_MODES,
        default="path",
        help="Sort the report by file path or by row count (descending).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = sort_results(scan_library(Path(args.path)), args.sort)
    print(format_report(results))  # noqa: T201


if __name__ == "__main__":
    main()
