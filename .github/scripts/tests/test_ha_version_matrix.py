"""Tests for the Home Assistant compatibility matrix."""

from __future__ import annotations

from typing import Any

import ha_version_matrix
import pytest


@pytest.mark.parametrize(
    "home_assistant_pin,expected",
    [
        ("2026.9.0", (2026, 9, 0)),
        ("2026.9.0b6", (2026, 9, -1)),
        ("2026.9.1rc2", (2026, 9, 0)),
    ],
)
def test_fetch_max_supported_version_caps_prereleases(
    monkeypatch: pytest.MonkeyPatch,
    home_assistant_pin: str,
    expected: tuple[int, int, int],
) -> None:
    """A prerelease plugin pin must not enable its corresponding stable release."""
    response: dict[str, Any] = {
        "info": {
            "version": "0.13.362",
            "requires_dist": [f"homeassistant=={home_assistant_pin}"],
        },
    }
    monkeypatch.setattr(ha_version_matrix, "fetch_pypi_json", lambda _url: response)

    assert ha_version_matrix.fetch_max_supported_version() == expected


def test_fetch_max_supported_version_accepts_environment_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment markers after an exact stable pin remain supported."""
    response: dict[str, Any] = {
        "info": {
            "version": "0.13.362",
            "requires_dist": ['homeassistant==2026.8.3; python_version >= "3.14"'],
        },
    }
    monkeypatch.setattr(ha_version_matrix, "fetch_pypi_json", lambda _url: response)

    assert ha_version_matrix.fetch_max_supported_version() == (2026, 8, 3)
