"""Tests for public power profile library URLs."""

import pytest

from custom_components.powercalc.power_profile.library_url import profile_url


@pytest.mark.parametrize(
    "manufacturer,model,expected",
    [
        ("signify", "LCT010", "https://library.powercalc.nl/profiles/signify/lct010"),
        (
            "AVM",
            "FRITZ!Box 5690 Pro",
            "https://library.powercalc.nl/profiles/avm/fritz-box-5690-pro",
        ),
        (
            "Société Énergie",
            "Prise № 1",
            "https://library.powercalc.nl/profiles/societe-energie/prise-no-1",
        ),
        (
            "智能家居",
            "插座 2",
            "https://library.powercalc.nl/profiles/%E6%99%BA%E8%83%BD%E5%AE%B6%E5%B1%85/%E6%8F%92%E5%BA%A7-2",
        ),
    ],
)
def test_profile_url(manufacturer: str, model: str, expected: str) -> None:
    assert profile_url(manufacturer, model) == expected
