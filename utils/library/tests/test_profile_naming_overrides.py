from __future__ import annotations

import glob
import json
import os

from utils.library.common import PROFILE_DIRECTORY

# Sensor naming is a user preference, configured globally or per sensor. Profiles must not override it.
# `only_self_usage` profiles get the "{} Device Power" naming injected by PowerProfile.sensor_config,
# so they should not repeat it in their model.json either.
NAMING_OPTIONS = (
    "power_sensor_naming",
    "power_sensor_friendly_naming",
    "energy_sensor_naming",
    "energy_sensor_friendly_naming",
)


def test_no_profile_overrides_sensor_naming() -> None:
    offenders = []
    for file_path in sorted(glob.glob(os.path.join(PROFILE_DIRECTORY, "*/*/model.json"))):
        with open(file_path) as file:
            model_json = json.load(file)
        for scope in (model_json, model_json.get("sensor_config") or {}):
            offenders.extend(f"{file_path}: {option}" for option in NAMING_OPTIONS if option in scope)

    assert not offenders, "Profiles must not override sensor naming:\n" + "\n".join(offenders)
