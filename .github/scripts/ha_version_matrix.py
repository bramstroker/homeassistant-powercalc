"""Build the Home Assistant version matrix for the test workflow.

Emits the highest stable patch of each supported month that has a matching test plugin,
along with the Python version and plugin requirement. The result is a `versions=[...]`
line for `$GITHUB_OUTPUT`.

Each release is pinned to the lowest Python it declares support for. That is the interpreter
the release was actually built against, so an older Home Assistant never gets handed a Python
that did not exist yet when it was published.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any
import urllib.error
import urllib.request

PYPI_URL = "https://pypi.org/pypi/homeassistant/json"
OFFICIAL_PLUGIN_URL = "https://pypi.org/pypi/pytest-homeassistant/json"
LEGACY_PLUGIN_URL = "https://pypi.org/pypi/pytest-homeassistant-custom-component/json"
FIRST_OFFICIAL_MONTH = (2026, 11)
CONST_FILE = "custom_components/powercalc/const.py"
STABLE_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
PYTHON_FLOOR = re.compile(r">=\s*(\d+)\.(\d+)")
PLUGIN_HA_PIN = re.compile(r"^homeassistant\s*==\s*(\d+)\.(\d+)\.(\d+)([^\s;]*)\s*(?:;.*)?$")


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


def fetch_pypi_json(url: str) -> dict[str, Any]:
    """Fetch a PyPI JSON document, retrying a few times on network trouble."""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
                return json.load(response)  # type: ignore[no-any-return]
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            time.sleep(2**attempt)

    raise RuntimeError(f"Could not fetch {url} from PyPI: {last_error}")


def fetch_releases(url: str) -> dict[str, str]:
    """Fetch published versions from PyPI, mapped to their requires-python."""
    return {
        version: next((file["requires_python"] for file in files if file.get("requires_python")), "")
        for version, files in fetch_pypi_json(url)["releases"].items()
        if files
    }


def fetch_legacy_max_version() -> tuple[int, int, int]:
    """Read the legacy plugin's newest Home Assistant pin, excluding a prerelease pin."""
    info = fetch_pypi_json(LEGACY_PLUGIN_URL)["info"]
    for requirement in info.get("requires_dist") or []:
        pin = PLUGIN_HA_PIN.match(requirement)
        if pin:
            patch = int(pin.group(3))
            if pin.group(4):
                patch -= 1
            return int(pin.group(1)), int(pin.group(2)), patch

    raise RuntimeError(f"pytest-homeassistant-custom-component {info['version']} does not pin a Home Assistant release")


def python_version_for(release: str, requires_python: str) -> str:
    """Return the lowest Python version a release supports, as `major.minor`."""
    floor = PYTHON_FLOOR.search(requires_python)
    if not floor:
        raise RuntimeError(f"Could not read a Python version from {requires_python!r} of Home Assistant {release}")

    return f"{floor.group(1)}.{floor.group(2)}"


def build_matrix(
    releases: dict[str, str],
    min_version: tuple[int, int],
    official_versions: set[str],
    legacy_max_version: tuple[int, int, int] | None,
) -> list[dict[str, str]]:
    """Pick the highest stable patch with a test plugin for each supported month."""
    latest_per_month: dict[tuple[int, int], tuple[int, dict[str, str]]] = {}
    for release in releases:
        version = STABLE_VERSION.match(release)
        if not version:
            continue

        month = (int(version.group(1)), int(version.group(2)))
        if month < min_version:
            continue

        patch = int(version.group(3))
        known = latest_per_month.get(month)
        if known is not None and patch <= known[0]:
            continue

        if release in official_versions:
            test_plugin = f"pytest-homeassistant=={release}"
        elif month < FIRST_OFFICIAL_MONTH and legacy_max_version is not None and (*month, patch) <= legacy_max_version:
            test_plugin = "pytest-homeassistant-custom-component>=0.13"
        else:
            continue

        latest_per_month[month] = (
            patch,
            {
                "ha_version": release,
                "python_version": python_version_for(release, releases[release]),
                "test_plugin": test_plugin,
            },
        )

    return [target for _, (_, target) in sorted(latest_per_month.items())]


def main() -> None:
    min_version = read_min_version()
    legacy_max_version = fetch_legacy_max_version() if min_version < FIRST_OFFICIAL_MONTH else None
    versions = build_matrix(
        fetch_releases(PYPI_URL), min_version, set(fetch_releases(OFFICIAL_PLUGIN_URL)), legacy_max_version
    )
    print(f"versions={json.dumps(versions)}")


if __name__ == "__main__":
    main()
