"""Build the Home Assistant version matrix for the test workflow.

Emits every monthly Home Assistant release from `MIN_HA_VERSION` up to the newest stable one,
using the highest patch release of each month, paired with the Python version to test it on.
The result is written as a `versions=[...]` line, ready to be appended to `$GITHUB_OUTPUT`.

Each release is pinned to the lowest Python it declares support for. That is the interpreter
the release was actually built against, so an older Home Assistant never gets handed a Python
that did not exist yet when it was published.
"""

import json
import re
import time
import urllib.error
import urllib.request

PYPI_URL = "https://pypi.org/pypi/homeassistant/json"
CONST_FILE = "custom_components/powercalc/const.py"
STABLE_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
PYTHON_FLOOR = re.compile(r">=\s*(\d+)\.(\d+)")


def read_min_version() -> tuple[int, int]:
    """Read MIN_HA_VERSION from the integration constants."""
    with open(CONST_FILE) as const_file:
        match = re.search(r'^MIN_HA_VERSION\s*=\s*"([^"]+)"', const_file.read(), re.MULTILINE)

    if not match:
        raise RuntimeError(f"MIN_HA_VERSION not found in {CONST_FILE}")

    version = STABLE_VERSION.match(match.group(1))
    if not version:
        raise RuntimeError(f"MIN_HA_VERSION is not a stable version: {match.group(1)}")

    return int(version.group(1)), int(version.group(2))


def fetch_releases() -> dict[str, str]:
    """Fetch all published homeassistant versions from PyPI, mapped to their requires-python."""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(PYPI_URL, timeout=30) as response:  # noqa: S310
                releases = json.load(response)["releases"]
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            time.sleep(2**attempt)
        else:
            return {
                version: next((file["requires_python"] for file in files if file.get("requires_python")), "")
                for version, files in releases.items()
                if files
            }

    raise RuntimeError(f"Could not fetch releases from PyPI: {last_error}")


def python_version_for(release: str, requires_python: str) -> str:
    """Return the lowest Python version a release supports, as `major.minor`."""
    floor = PYTHON_FLOOR.search(requires_python)
    if not floor:
        raise RuntimeError(f"Could not read a Python version from {requires_python!r} of Home Assistant {release}")

    return f"{floor.group(1)}.{floor.group(2)}"


def build_matrix(releases: dict[str, str], min_version: tuple[int, int]) -> list[dict[str, str]]:
    """Pick the highest patch release of every month at or after the minimum version."""
    latest_per_month: dict[tuple[int, int], tuple[int, str]] = {}
    for release in releases:
        version = STABLE_VERSION.match(release)
        if not version:
            continue

        month = (int(version.group(1)), int(version.group(2)))
        if month < min_version:
            continue

        patch = int(version.group(3))
        known = latest_per_month.get(month)
        if known is None or patch > known[0]:
            latest_per_month[month] = (patch, release)

    return [
        {"ha_version": release, "python_version": python_version_for(release, releases[release])}
        for _, (_, release) in sorted(latest_per_month.items())
    ]


def main() -> None:
    versions = build_matrix(fetch_releases(), read_min_version())
    print(f"versions={json.dumps(versions)}")


if __name__ == "__main__":
    main()
