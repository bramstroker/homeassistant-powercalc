from dataclasses import replace
import json
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
import pytest

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.helpers import resolve_related_entity_placeholder
from tests.common import assert_entity_state, mock_devices, mock_entities_in_registry, run_powercalc_setup, set_states

PLACEHOLDER = "entity_by_unique_id_suffix:_sensor_dock_status"


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("renamed", "sensor.renamed_dock"),
        ("other_device", None),
        ("other_integration", None),
        ("ambiguous", None),
        ("disabled_duplicate", None),
        ("disabled", None),
        ("missing", None),
        ("no_source_registry", None),
        ("no_device", None),
        ("wrong_suffix", None),
        ("empty_suffix", None),
        ("invalid_suffix", None),
    ],
)
def test_suffix_lookup(hass: HomeAssistant, scenario: str, expected: str | None) -> None:
    devices = mock_devices(hass, {"robot": {}, "other": {"via_device_id": "robot"}})
    entries = {
        "vacuum.robot": {"device_id": "robot", "platform": "mqtt", "unique_id": "RobotA_vacuum"},
        "sensor.renamed_dock": {
            "device_id": "robot",
            "platform": "mqtt",
            "unique_id": "RobotA_sensor_dock_status",
        },
        # A different integration on the same device and another robot must not interfere.
        "sensor.foreign": {"device_id": "robot", "platform": "other", "unique_id": "A_sensor_dock_status"},
        "sensor.other_robot": {"device_id": "other", "platform": "mqtt", "unique_id": "B_sensor_dock_status"},
    }
    if scenario == "other_device":
        entries["sensor.renamed_dock"]["device_id"] = "other"
    elif scenario == "other_integration":
        entries["sensor.renamed_dock"]["platform"] = "other"
    elif scenario in {"ambiguous", "disabled_duplicate"}:
        entries["sensor.duplicate"] = {
            "device_id": "robot",
            "platform": "mqtt",
            "unique_id": "Duplicate_sensor_dock_status",
        }
        if scenario == "disabled_duplicate":
            entries["sensor.duplicate"]["disabled_by"] = RegistryEntryDisabler.USER
    elif scenario == "disabled":
        entries["sensor.renamed_dock"]["disabled_by"] = RegistryEntryDisabler.USER
    elif scenario == "missing":
        del entries["sensor.renamed_dock"]
    elif scenario == "no_source_registry":
        del entries["vacuum.robot"]
    elif scenario == "wrong_suffix":
        entries["sensor.renamed_dock"]["unique_id"] = "RobotA_sensor_dock_status_extra"
    mock_entities_in_registry(hass, entries)
    source = SourceEntity("robot", "vacuum.robot", "vacuum", device_entry=devices["robot"])
    if scenario == "no_device":
        source = replace(source, device_entry=None)
    placeholder = {
        "empty_suffix": "entity_by_unique_id_suffix:",
        "invalid_suffix": "entity_by_unique_id_suffix:.*",
    }.get(scenario, PLACEHOLDER)
    assert resolve_related_entity_placeholder(hass, placeholder, source) == expected


@pytest.mark.parametrize("robot_id,entity_id", [("RobotA", "sensor.renamed_dock"), ("OtherRobot", "sensor.station")])
async def test_profile_resolves_suffix_across_installations(
    hass: HomeAssistant, tmp_path: Path, robot_id: str, entity_id: str
) -> None:
    mock_devices(hass, {"robot": {"manufacturer": "Valetudo"}})
    mock_entities_in_registry(
        hass,
        {
            "vacuum.robot": {"device_id": "robot", "platform": "mqtt", "unique_id": f"{robot_id}_vacuum"},
            entity_id: {"device_id": "robot", "platform": "mqtt", "unique_id": f"{robot_id}_sensor_dock_status"},
        },
    )
    (tmp_path / "model.json").write_text(
        json.dumps(
            {
                "name": "Valetudo dock",
                "calculation_strategy": "composite",
                "composite_config": {
                    "mode": "stop_at_first",
                    "strategies": [
                        {
                            "condition": {"condition": "state", "entity_id": f"[[{PLACEHOLDER}]]", "state": "drying"},
                            "fixed": {"power": 40},
                        },
                        {
                            "condition": {"condition": "state", "entity_id": f"[[{PLACEHOLDER}]]", "state": "idle"},
                            "fixed": {"power": 3},
                        },
                    ],
                },
            }
        )
    )
    await run_powercalc_setup(
        hass,
        {
            "entity_id": "vacuum.robot",
            "name": "Robot",
            "custom_model_directory": str(tmp_path),
        },
    )
    await set_states(hass, [("vacuum.robot", "docked"), (entity_id, "drying")])
    assert_entity_state(hass, "sensor.robot_power", "40.00")
    await set_states(hass, [(entity_id, "idle")])
    assert_entity_state(hass, "sensor.robot_power", "3.00")
