"""Fill in `device_specs` on light profiles from what their name already states.

The manufacturer normalization passes moved the socket, the shape, the brightness and the
rated power into the profile `name`: "Grid Connect Smart R80 CCT E27 Globe (9.5 W, 806 lm)"
carries four facts the library website would like to filter on, and none of them are in a
field. This reads them back out of the name, which is data that has already been through
human review, rather than looking anything up.

It is deliberately shy. A name that says something ambiguous yields nothing for that key: an
absent spec reads as "not stated", while a wrong one is a claim the site would present as
fact. Everything it skips is listed in the dry run, for whoever wants to fill those in by hand.

Run it to see what it would change, then again with --write to apply:

    python -m utils.library.extract_device_specs
    python -m utils.library.extract_device_specs --write
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import re
from typing import Any, NamedTuple

from utils.library.common import PROFILE_DIRECTORY

DATA_DIR = str(Path(PROFILE_DIRECTORY).resolve())

SOCKET_PATTERN = re.compile(r"\b(E27|E26|E14|E12|B22|GU10|GU5\.3|GU24|GX53|G9|G4)\b", re.IGNORECASE)

# Ordered by how specific each word is: "GU10 Spotlight Bulb" is a spot, and "Filament Globe
# Bulb" is a filament. The last entry only wins when nothing above it matched.
FORM_FACTOR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bdownlight\b", re.IGNORECASE), "downlight"),
    (
        re.compile(r"\b(?:light ?strip|led ?strip|striplight|neon rope|rope light|led band|flex)\b", re.IGNORECASE),
        "strip",
    ),
    (re.compile(r"\bstrip\b", re.IGNORECASE), "strip"),
    (re.compile(r"\bpanels?\b", re.IGNORECASE), "panel"),
    (re.compile(r"\btube\b", re.IGNORECASE), "tube"),
    (re.compile(r"\bcandle\b", re.IGNORECASE), "candle"),
    (re.compile(r"\bspot(?:light)?\b", re.IGNORECASE), "spot"),
    (re.compile(r"\bfilament\b", re.IGNORECASE), "filament"),
    (
        # A luminaire, named after where it hangs rather than what goes in it.
        re.compile(
            r"\b(?:ceiling|pendant|suspension|wall (?:light|lamp|washer)|"
            r"floor (?:lamp|light)|table lamp|desk lamp|bedside|under.?cabinet|"
            r"surface.?mounted|surface light|bollard|pedestal|flood ?light|"
            r"key light|ring light|mood ?light|moonlamp|"
            r"string(?:s| lights?)?|light chain|christmas lights)\b",
            re.IGNORECASE,
        ),
        "fixture",
    ),
    (re.compile(r"\bbulb\b", re.IGNORECASE), "bulb"),
]

# Shapes that hold their light source rather than take a lamp. A downlight or a tube is left
# out: those come in both integrated and GU10 or G13 versions, and the name rarely says which.
INTEGRATED_FORM_FACTORS = frozenset({"fixture", "panel", "strip"})

LUMENS_PATTERN = re.compile(r"\b(\d{2,5})\s?(?:lm|lumens?)\b", re.IGNORECASE)
# Two figures for two variants of the same lamp, e.g. "(450/470 lm)". Which one belongs to
# this profile is not something the name settles.
DUAL_LUMENS_PATTERN = re.compile(r"\d+\s*/\s*\d+\s*(?:lm|lumens?)\b", re.IGNORECASE)
WATTS_PATTERN = re.compile(r"\b(\d{1,3}(?:[.,]\d+)?)\s?W\b")

LUMENS_RANGE = (50, 25_000)
# A rated wattage sits near the measured maximum. Names also quote the incandescent bulb a
# lamp replaces — "60W=8.5W", "75W A19" — and those numbers are several times the real draw.
RATED_POWER_TOLERANCE = (0.5, 2.0)


class Extraction(NamedTuple):
    """What a profile name gave up, and what it would not say."""

    specs: dict[str, Any]
    skipped: list[str]


def extract_socket(name: str) -> tuple[str | list[str] | None, str | None]:
    sockets = {match.upper().replace("GU5.3", "GU5.3") for match in SOCKET_PATTERN.findall(name)}
    if len(sockets) > 1:
        return sorted(sockets), None
    if not sockets:
        return None, None
    return sockets.pop(), None


def extract_form_factor(name: str) -> str | None:
    """Return the shape the name states.

    "Globe" is left out on purpose: half the library means a spherical G95 by it and the
    other half, Australian and British brands, mean any bulb at all.
    """
    for pattern, form_factor in FORM_FACTOR_PATTERNS:
        if pattern.search(name):
            return form_factor
    return None


def extract_lumens(name: str) -> tuple[int | None, str | None]:
    if DUAL_LUMENS_PATTERN.search(name):
        return None, "quotes two brightness figures"

    candidates = [int(match) for match in LUMENS_PATTERN.findall(name)]
    in_range = [value for value in candidates if LUMENS_RANGE[0] <= value <= LUMENS_RANGE[1]]
    if len(in_range) != 1:
        return None, "quotes two brightness figures" if len(in_range) > 1 else None
    return in_range[0], None


def extract_rated_power(name: str, max_power: float | None) -> tuple[float | None, str | None]:
    """Return the rated wattage, checked against what the profile actually measured."""
    candidates = [float(match.replace(",", ".")) for match in WATTS_PATTERN.findall(name)]
    if not candidates:
        return None, None
    if max_power is None or max_power <= 0:
        return None, "states a wattage, but the profile has no measured maximum to check it against"

    plausible = [
        value
        for value in candidates
        if max_power * RATED_POWER_TOLERANCE[0] <= value <= max_power * RATED_POWER_TOLERANCE[1]
    ]
    if len(plausible) != 1:
        quoted = ", ".join(f"{value:g} W" for value in candidates)
        return None, f"states {quoted} against a measured {max_power:g} W"
    return plausible[0], None


def extract_specs(name: str, max_power: float | None = None) -> Extraction:
    """Read every spec a light's name states, and record what it was too vague about."""
    specs: dict[str, Any] = {}
    skipped: list[str] = []

    socket, socket_skip = extract_socket(name)
    if socket:
        specs["socket"] = socket
    if socket_skip:
        skipped.append(socket_skip)

    form_factor = extract_form_factor(name)
    if form_factor:
        specs["form_factor"] = form_factor
        # Nothing screws into a light panel or a ceiling lamp.
        if not socket and form_factor in INTEGRATED_FORM_FACTORS:
            specs["socket"] = "integrated"

    lumens, lumens_skip = extract_lumens(name)
    if lumens:
        specs["lumens"] = lumens
    if lumens_skip:
        skipped.append(lumens_skip)

    rated_power, power_skip = extract_rated_power(name, max_power)
    if rated_power:
        specs["rated_power"] = rated_power
    if power_skip:
        skipped.append(power_skip)

    return Extraction(specs, skipped)


def load_max_powers() -> dict[str, float]:
    """Measured maxima per profile, from the generated library index."""
    library_path = Path(DATA_DIR) / "library.json"
    if not library_path.is_file():
        return {}

    library = json.loads(library_path.read_text(encoding="utf-8"))
    return {
        f"{manufacturer['dir_name']}/{model['id']}": model["max_power"]
        for manufacturer in library["manufacturers"]
        for model in manufacturer["models"]
        if model.get("max_power")
    }


def add_device_specs(model_data: dict[str, Any], specs: dict[str, Any]) -> dict[str, Any]:
    """Return the model carrying `specs`, next to the device type they describe.

    Existing values win. A later pass fills the gaps an earlier one left, and never argues
    with a spec somebody has already written by hand.
    """
    merged = {**specs, **(model_data.get("device_specs") or {})}
    updated: dict[str, Any] = {}
    for key, value in model_data.items():
        updated[key] = merged if key == "device_specs" else value
        if key == "device_type" and "device_specs" not in model_data:
            updated["device_specs"] = merged
    if "device_specs" not in updated:
        updated["device_specs"] = merged
    return updated


def missing_specs(model_data: dict[str, Any], specs: dict[str, Any]) -> dict[str, Any]:
    """The subset of `specs` the profile does not already carry."""
    existing = model_data.get("device_specs") or {}
    return {key: value for key, value in specs.items() if key not in existing}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Apply the changes instead of listing them")
    args = parser.parse_args()

    max_powers = load_max_powers()
    changed = 0
    skipped_profiles: list[tuple[str, list[str]]] = []
    counts: dict[str, int] = {"socket": 0, "form_factor": 0, "lumens": 0, "rated_power": 0}

    for path in sorted(glob.glob(f"{DATA_DIR}/*/*/model.json")):
        model_path = Path(path)
        model_data = json.loads(model_path.read_text(encoding="utf-8"))
        if model_data.get("device_type") != "light":
            continue

        profile = "/".join(model_path.parts[-3:-1])
        extraction = extract_specs(model_data.get("name") or "", max_powers.get(profile))
        if extraction.skipped:
            skipped_profiles.append((profile, extraction.skipped))

        additions = missing_specs(model_data, extraction.specs)
        if not additions:
            continue

        changed += 1
        for key in additions:
            counts[key] += 1
        print(f"{profile}: {json.dumps(additions)}")  # noqa: T201

        if args.write:
            updated = add_device_specs(model_data, additions)
            model_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n{changed} profiles {'updated' if args.write else 'would be updated'}")  # noqa: T201
    for key, count in counts.items():
        print(f"  {key}: {count}")  # noqa: T201

    if skipped_profiles:
        print(f"\n{len(skipped_profiles)} profiles left for a human to decide:")  # noqa: T201
        for profile, reasons in skipped_profiles:
            print(f"  {profile}: {'; '.join(reasons)}")  # noqa: T201

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
