from dataclasses import replace

from measure.analyser.entity_references import resolve_portable_entity
from measure.recording.models import RecordedEntity, RecorderProfileRecipe, RecordingContext
import pytest


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("renamed", True),
        ("other_device", False),
        ("related_device", False),
        ("other_integration", False),
        ("no_integration", False),
        ("no_unique_id", False),
        ("wrong_suffix", False),
        ("ambiguous", False),
        ("disabled_duplicate", False),
        ("invalid_suffix", False),
        ("empty_suffix", False),
        ("missing_identity", False),
    ],
)
def test_portable_unique_id_suffix(scenario: str, expected: bool) -> None:
    primary = RecordedEntity("vacuum.robot", "vacuum", "primary", device_id="robot", integration="mqtt")
    dock = RecordedEntity(
        "sensor.renamed",
        "sensor",
        "tracked",
        device_id="robot",
        integration="mqtt",
        unique_id="RobotA_sensor_dock_status",
    )
    suffix = {"invalid_suffix": ".*", "empty_suffix": ""}.get(scenario, "_sensor_dock_status")
    related = []
    if scenario in {"other_device", "related_device"}:
        dock = replace(dock, device_id="other")
        if scenario == "related_device":
            related = ["other"]
    elif scenario == "other_integration":
        dock = replace(dock, integration="other")
    elif scenario == "no_integration":
        primary = replace(primary, integration=None)
    elif scenario == "no_unique_id":
        dock = replace(dock, unique_id=None)
    elif scenario == "wrong_suffix":
        dock = replace(dock, unique_id="RobotA_sensor_dock_status_extra")
    elif scenario == "missing_identity":
        dock = replace(dock, device_id=None)
    inventory = [
        primary,
        dock,
        replace(dock, entity_id="sensor.foreign", integration="other"),
        replace(dock, entity_id="sensor.other_robot", device_id="second_robot"),
    ]
    if scenario in {"ambiguous", "disabled_duplicate"}:
        inventory.append(
            replace(
                dock,
                entity_id="sensor.duplicate",
                unique_id="B_sensor_dock_status",
                disabled_by="user" if scenario == "disabled_duplicate" else None,
            )
        )
    context = RecordingContext(
        RecorderProfileRecipe.VACUUM_ROBOT,
        primary.entity_id,
        "vacuum_robot",
        [primary, dock],
        device_entities=inventory,
        related_device_ids=related,
    )
    reference = resolve_portable_entity(dock.entity_id, context, unique_id_suffix=suffix)
    assert reference == ("[[entity_by_unique_id_suffix:_sensor_dock_status]]" if expected else None)
    # A suffix must be supplied by a known mapping, never guessed from the identifier.
    assert resolve_portable_entity(dock.entity_id, context) is None
