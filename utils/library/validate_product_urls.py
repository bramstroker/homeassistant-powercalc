"""Validate that product URLs in power profiles resolve to an accepted HTTP status."""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from utils.library.common import PROFILE_DIRECTORY

DEFAULT_TIMEOUT = 20.0
DEFAULT_WORKERS = 8
DEFAULT_FAILURE_THRESHOLD = 1
MODEL_FILE_NAME = "model.json"
STATUS_ALLOWLIST_PATH = Path(__file__).with_name("product_url_status_allowlist.json")
USER_AGENT = "PowerCalc profile-library URL validator (+https://github.com/bramstroker/homeassistant-powercalc)"


@dataclass(frozen=True)
class ProductUrlResult:
    """The result of checking one unique product URL."""

    url: str
    status: int | None
    final_url: str | None = None
    error: str | None = None
    allowlist_reason: str | None = None

    @property
    def valid(self) -> bool:
        """Return whether the URL ended in HTTP 200 or an explicitly allowed status."""
        return self.status == 200 or self.allowlist_reason is not None


@dataclass(frozen=True)
class StatusAllowlistEntry:
    """Non-200 statuses accepted for one URL, with a human-readable justification."""

    statuses: frozenset[int]
    reason: str


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return cast(dict[str, Any], json.load(file))


def load_status_allowlist(path: Path = STATUS_ALLOWLIST_PATH) -> dict[str, StatusAllowlistEntry]:
    """Load explicitly accepted non-200 statuses for known bot-blocking product pages."""
    entries = _load_json(path)
    return {
        url: StatusAllowlistEntry(
            statuses=frozenset(entry["statuses"]),
            reason=entry["reason"],
        )
        for url, entry in entries.items()
    }


def load_failure_counts(path: Path | None) -> dict[str, int]:
    """Load consecutive failure counts, treating a missing state file as a first run."""
    if path is None or not path.is_file():
        return {}
    return {url: int(count) for url, count in _load_json(path).items()}


def update_failure_counts(
    results: list[ProductUrlResult],
    previous_counts: dict[str, int],
) -> dict[str, int]:
    """Increment failed URLs and reset successful or removed URLs by omitting them."""
    return {result.url: previous_counts.get(result.url, 0) + 1 for result in results if not result.valid}


def write_failure_counts(path: Path, failure_counts: dict[str, int]) -> None:
    """Persist consecutive failure counts for the next scheduled run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(failure_counts, indent=2, sort_keys=True)}\n", encoding="utf-8")


def model_files(paths: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_file() and path.name == MODEL_FILE_NAME:
            files.add(path)
        elif path.is_dir():
            files.update(path.glob(f"**/{MODEL_FILE_NAME}"))
    return sorted(files)


def changed_model_files(changed_files_path: Path) -> list[Path]:
    changed_files = json.loads(changed_files_path.read_text(encoding="utf-8"))
    return sorted(
        path
        for value in changed_files
        if (path := Path(value)).name == MODEL_FILE_NAME
        and path.parts[:1] == (Path(PROFILE_DIRECTORY).name,)
        and path.is_file()
    )


def collect_product_urls(model_files: list[Path]) -> dict[str, list[Path]]:
    """Collect unique product URLs and the model files which reference them."""
    profiles_by_url: defaultdict[str, list[Path]] = defaultdict(list)
    for path in model_files:
        product_url = _load_json(path).get("product_url")
        if isinstance(product_url, str):
            profiles_by_url[product_url].append(path)
    return dict(sorted(profiles_by_url.items()))


def check_product_url(
    url: str,
    timeout: float,
    allowlist_entry: StatusAllowlistEntry | None = None,
) -> ProductUrlResult:
    """Follow redirects and require HTTP 200 or an explicitly accepted status."""
    if urlparse(url).scheme != "https":
        return ProductUrlResult(url=url, status=None, error="URL must use HTTPS")

    request = Request(  # noqa: S310 - HTTPS is enforced above.
        url,
        headers={"Accept": "text/html,*/*;q=0.8", "User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - HTTPS is enforced above.
            return ProductUrlResult(url=url, status=response.status, final_url=response.geturl())
    except HTTPError as error:
        return ProductUrlResult(
            url=url,
            status=error.code,
            final_url=error.url,
            error=str(error.reason),
            allowlist_reason=(
                allowlist_entry.reason if allowlist_entry and error.code in allowlist_entry.statuses else None
            ),
        )
    except (TimeoutError, URLError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        return ProductUrlResult(url=url, status=None, error=str(reason))


def validate_product_urls(
    profiles_by_url: dict[str, list[Path]],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    workers: int = DEFAULT_WORKERS,
    status_allowlist: dict[str, StatusAllowlistEntry] | None = None,
) -> list[ProductUrlResult]:
    """Validate all unique product URLs concurrently."""
    status_allowlist = status_allowlist or {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda url: check_product_url(url, timeout, status_allowlist.get(url)),
                profiles_by_url,
            )
        )


def build_report(
    results: list[ProductUrlResult],
    profiles_by_url: dict[str, list[Path]],
    failure_counts: dict[str, int] | None = None,
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
) -> str:
    """Build a concise validation report."""
    failure_counts = failure_counts or {}
    failures = [result for result in results if not result.valid]
    if not failures:
        allowlisted = sum(result.allowlist_reason is not None for result in results)
        suffix = f" ({allowlisted} accepted through the non-200 allowlist.)" if allowlisted else ""
        return f"All {len(results)} product URL(s) passed validation.{suffix}"

    threshold_failures = [result for result in failures if failure_counts.get(result.url, 1) >= failure_threshold]
    if threshold_failures:
        lines = [
            (
                f"Product URL validation failed for {len(threshold_failures)} of {len(results)} URL(s) "
                f"after {failure_threshold} consecutive check(s):"
            )
        ]
    else:
        lines = [
            (
                f"Product URL validation found {len(failures)} transient failure(s); "
                f"the {failure_threshold}-check notification threshold was not reached:"
            )
        ]
    for result in failures:
        outcome = f"HTTP {result.status}" if result.status is not None else result.error or "request failed"
        count = failure_counts.get(result.url, 1)
        lines.append(f"- `{result.url}` — {outcome} — consecutive failures: {count}/{failure_threshold}")
        lines.extend(f"  - `{path}`" for path in profiles_by_url[result.url])
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, default=[Path(PROFILE_DIRECTORY)])
    parser.add_argument("--changed-files", type=Path, help="JSON array of changed repository paths to validate")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--status-allowlist", type=Path, default=STATUS_ALLOWLIST_PATH)
    parser.add_argument("--failure-state", type=Path, help="JSON state from the previous validation run")
    parser.add_argument("--failure-state-output", type=Path, help="Write updated JSON state for the next run")
    parser.add_argument("--failure-threshold", type=int, default=DEFAULT_FAILURE_THRESHOLD)
    parser.add_argument("--report", type=Path, help="Append the result to a Markdown report")
    parser.add_argument("--status", type=Path, help="Write failure here when the consecutive-failure threshold is met")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Validate selected profile product URLs and return a process exit code."""
    args = _parse_args(argv)
    selected_model_files = changed_model_files(args.changed_files) if args.changed_files else model_files(args.paths)
    profiles_by_url = collect_product_urls(selected_model_files)
    results = validate_product_urls(
        profiles_by_url,
        timeout=args.timeout,
        workers=args.workers,
        status_allowlist=load_status_allowlist(args.status_allowlist),
    )
    failure_counts = update_failure_counts(results, load_failure_counts(args.failure_state))
    report = build_report(results, profiles_by_url, failure_counts, args.failure_threshold)
    print(report)  # noqa: T201

    failed = any(count >= args.failure_threshold for count in failure_counts.values())
    if args.failure_state_output:
        write_failure_counts(args.failure_state_output, failure_counts)
    if args.report:
        with args.report.open("a", encoding="utf-8") as file:
            file.write(f"\n\n## Product URLs\n\n{report}\n")
    if failed and args.status:
        args.status.write_text("failure", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
