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
def test_fetch_legacy_max_version_caps_prereleases(
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

    assert ha_version_matrix.fetch_legacy_max_version() == expected


def test_fetch_legacy_max_version_accepts_environment_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment markers after an exact stable pin remain supported."""
    response: dict[str, Any] = {
        "info": {
            "version": "0.13.362",
            "requires_dist": ['homeassistant==2026.8.3; python_version >= "3.14"'],
        },
    }
    monkeypatch.setattr(ha_version_matrix, "fetch_pypi_json", lambda _url: response)

    assert ha_version_matrix.fetch_legacy_max_version() == (2026, 8, 3)


def test_build_matrix_selects_matching_test_plugins() -> None:
    """Use the highest compatible stable patch in each supported month."""
    releases = dict.fromkeys(
        ["2026.5.4", "2026.6.4", "2026.10.5", "2026.10.4", "2026.11.2", "2026.11.1", "2026.12.0b1"],
        ">=3.14.2",
    )

    matrix = ha_version_matrix.build_matrix(
        releases,
        min_version=(2026, 6),
        official_versions={"2026.11.1", "2026.12.0b1"},
        legacy_max_version=(2026, 10, 4),
    )

    assert matrix == [
        {
            "ha_version": "2026.6.4",
            "python_version": "3.14",
            "test_plugin": "pytest-homeassistant-custom-component>=0.13",
        },
        {
            "ha_version": "2026.10.4",
            "python_version": "3.14",
            "test_plugin": "pytest-homeassistant-custom-component>=0.13",
        },
        {"ha_version": "2026.11.1", "python_version": "3.14", "test_plugin": "pytest-homeassistant==2026.11.1"},
    ]
