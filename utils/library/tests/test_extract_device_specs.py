from __future__ import annotations

import pytest

from utils.library.extract_device_specs import add_device_specs, extract_specs, missing_specs


def test_reads_every_spec_a_well_formed_name_states() -> None:
    extraction = extract_specs("Grid Connect Smart R80 CCT E27 Globe (9.5 W, 806 lm)", max_power=9.37)

    assert extraction.specs == {"socket": "E27", "lumens": 806, "rated_power": 9.5}
    assert extraction.skipped == []


@pytest.mark.parametrize(
    "name, expected",
    [
        ("TRADFRI bulb E14 WW clear 250lm", "E14"),
        ("Smart Zigbee Pro GU10 Spotlight Bulb", "GU10"),
        ("Philips Hue White Ambiance GU5.3/MR16", "GU5.3"),
        ("Hue White Bulb A60 B22", "B22"),
    ],
)
def test_reads_the_socket(name: str, expected: str) -> None:
    assert extract_specs(name).specs["socket"] == expected


def test_reads_all_sockets_when_a_profile_covers_regional_variants() -> None:
    extraction = extract_specs("Hue White and Color Ambiance A19 E26/E27 (Gen 5)")

    assert extraction.specs["socket"] == ["E26", "E27"]
    assert extraction.skipped == []


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Smart Zigbee Pro GU10 Spotlight Bulb", "spot"),
        ("Hue G125 E27 Filament Globe Bulb", "filament"),
        ("Nue RGBW Downlight", "downlight"),
        ("Hue Gradient Lightstrip", "strip"),
        ("Wi-Fi 7W LED Tube Lamp", "tube"),
        ("Livarno Home E14 CCT Candle Bulb", "candle"),
        ("Areo VariFit Round Recessed Panel", "panel"),
        ("Smart Bulb Colour E27", "bulb"),
    ],
)
def test_reads_the_shape_most_specific_word_first(name: str, expected: str) -> None:
    assert extract_specs(name).specs["form_factor"] == expected


def test_ignores_globe_which_means_two_different_things() -> None:
    """Half the library means a spherical G95 by it, the other half means any bulb at all."""
    assert "form_factor" not in extract_specs("KAJPLATS E27 WS globe 806lm").specs


def test_leaves_the_brightness_out_when_a_name_offers_two() -> None:
    extraction = extract_specs("TRADFRI E12/E14 White Spectrum Globe Bulb (450/470 lm)")

    assert "lumens" not in extraction.specs
    assert "quotes two brightness figures" in extraction.skipped


def test_rejects_the_incandescent_bulb_a_lamp_replaces() -> None:
    """ "60W=8.5W" quotes an equivalence first. The measurement says which is the real one."""
    extraction = extract_specs("Wifi LED Smart Light Bulb, 60W=8.5W, Full Color A19", max_power=8.9)

    assert extraction.specs["rated_power"] == 8.5
    assert extraction.skipped == []


def test_leaves_out_a_wattage_the_measurement_contradicts() -> None:
    extraction = extract_specs("Hue White and color ambiance 75W A19- E26 smart bulb", max_power=8.38)

    assert "rated_power" not in extraction.specs
    assert extraction.skipped == ["states 75 W against a measured 8.38 W"]


def test_leaves_out_a_wattage_it_cannot_check() -> None:
    extraction = extract_specs("Smart Color 15W", max_power=None)

    assert "rated_power" not in extraction.specs
    assert extraction.skipped == [
        "states a wattage, but the profile has no measured maximum to check it against",
    ]


def test_reads_a_wattage_written_with_a_comma() -> None:
    assert extract_specs("Hue smart bulb G93 warm white E27 7,2W", max_power=7.1).specs["rated_power"] == 7.2


def test_says_nothing_about_a_name_that_states_nothing() -> None:
    assert extract_specs("Kasa Smart Wi-Fi Light", max_power=9.0) == ({}, [])


def test_device_specs_land_next_to_the_device_type() -> None:
    model = {"name": "A light", "device_type": "light", "standby_power": 0.4}

    updated = add_device_specs(model, {"socket": "E27"})

    assert list(updated) == ["name", "device_type", "device_specs", "standby_power"]


def test_device_specs_are_appended_when_there_is_no_device_type() -> None:
    updated = add_device_specs({"name": "A light"}, {"socket": "E27"})

    assert list(updated) == ["name", "device_specs"]


@pytest.mark.parametrize(
    "name",
    [
        "Hue Being Ceiling Light",
        "NYMANE pendant lamp",
        "Hue Cher Suspension Light",
        "Hue Sana Wall Light",
        "Lyra RGBICWW Corner Floor Lamp",
        "Hue Wellness White Ambiance Table lamp",
        "Mi LED Desk Lamp 1S",
        "SLAGSIDA Under-Cabinet Light (60 cm)",
        "FUEVA-Z Surface-Mounted Light (285mm)",
        "Hue Calla outdoor bollard",
        "Hue Discover white and color ambiance flood light",
        "Key Light Air",
        "Smart String Lights",
        "Melinera Christmas Lights",
        "Livarno outdoor LED light chain",
        "Livarno Lux smart LED mood light",
    ],
)
def test_a_luminaire_is_a_fixture_that_takes_no_lamp(name: str) -> None:
    assert extract_specs(name).specs == {"form_factor": "fixture", "socket": "integrated"}


@pytest.mark.parametrize(
    "name, form_factor",
    [
        ("Glide Hexa Light Panels (10 panels)", "panel"),
        ("Neon Rope Light", "strip"),
        ("SMART+ ZB Flex 3P RGB + TW", "strip"),
        ("Hue OmniGlow striplight 3m", "strip"),
    ],
)
def test_a_panel_or_a_strip_holds_its_own_light_source(name: str, form_factor: str) -> None:
    assert extract_specs(name).specs == {"form_factor": form_factor, "socket": "integrated"}


@pytest.mark.parametrize("name", ["Wi-Fi Dimmable RGB+CCT 9W LED Downlight", "Wi-Fi 7W LED Tube Lamp"])
def test_a_downlight_or_a_tube_is_left_alone(name: str) -> None:
    """Both ship as integrated units and as fittings for a GU10 or a G13, and names rarely say."""
    assert "socket" not in extract_specs(name).specs


def test_a_stated_socket_beats_the_integrated_rule() -> None:
    assert extract_specs("Smart Zigbee GU10 Ceiling Spotlight").specs["socket"] == "GU10"


def test_an_existing_spec_is_never_argued_with() -> None:
    model = {"device_type": "light", "device_specs": {"socket": "E14", "lumens": 470}}

    updated = add_device_specs(model, {"socket": "E27", "form_factor": "candle"})

    assert updated["device_specs"] == {"socket": "E14", "lumens": 470, "form_factor": "candle"}


def test_only_the_gaps_are_proposed() -> None:
    model = {"device_specs": {"socket": "E27"}}

    assert missing_specs(model, {"socket": "E14", "lumens": 806}) == {"lumens": 806}
