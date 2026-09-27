import json
from pathlib import Path

from measure.analyser.recording import load_recording, restore_recording_context
from measure.analyser.vacuum.signals import suggest_recording_entities
from measure.ha_app.entity_suggestions import add_recording_suggestions
from measure.home_assistant.entities import EntityCatalogSnapshot, EntityDescriptor
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.recording.context import build_recording_context
from measure.recording.models import EntityRole
from measure.request import RecorderMeasurementRequest, RecorderProfileRecipe, RecorderPurpose
import pytest


def test_valetudo_identity_survives_recording_round_trip(tmp_path: Path) -> None:
    descriptors = [
        EntityDescriptor(
            entity_id=entity_id,
            name=entity_id,
            domain=entity_id.partition(".")[0],
            device_id="robot",
            integration="mqtt",
            manufacturer="Valetudo",
            unique_id=unique_id,
            state="idle",
            attribute_names=[],
        )
        for entity_id, unique_id in [
            ("vacuum.robot", "RobotA_vacuum"),
            ("sensor.battery", "RobotA_sensor_battery_level"),
            ("sensor.renamed_dock", "RobotA_sensor_dock_status"),
        ]
    ]
    suggested = add_recording_suggestions(EntityCatalogSnapshot(descriptors))
    vacuum = next(entity for entity in suggested if entity.domain == "vacuum")
    assert vacuum.suggested_recording_entity_ids == ["sensor.renamed_dock"]
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id="vacuum.robot",
        battery_entity_id="sensor.battery",
        additional_entity_ids=("sensor.renamed_dock",),
    )
    context = build_recording_context(request, descriptors)
    path = tmp_path / "record.jsonl"
    path.write_text(json.dumps(context.build_metadata_record()) + "\n")
    metadata = load_recording(path).dataset.metadata
    restored = restore_recording_context(build_recording_context(request), metadata)
    assert restored.entities == context.entities
    assert restored.device_entities == context.device_entities
    assert suggest_recording_entities(restored).selected == ["sensor.renamed_dock"]


def test_vacuum_context_records_selected_metadata_and_complete_device_inventory() -> None:
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id="vacuum.robot",
        battery_entity_id="sensor.battery",
        additional_entity_ids=("sensor.state",),
    )
    descriptors = [
        EntityDescriptor(
            entity_id="vacuum.robot",
            name="Robot",
            domain="vacuum",
            device_id="robot",
            state="docked",
            attribute_names=[],
            integration="dreame_vacuum",
        ),
        EntityDescriptor(
            entity_id="sensor.state",
            name="State",
            domain="sensor",
            device_id="robot",
            state="idle",
            attribute_names=[],
            translation_key="state",
            integration="dreame_vacuum",
        ),
        EntityDescriptor(
            entity_id="sensor.disabled",
            name="Disabled",
            domain="sensor",
            device_id="robot",
            state="unavailable",
            attribute_names=[],
            disabled_by="integration",
            has_live_state=False,
        ),
        EntityDescriptor(
            entity_id="sensor.unrelated",
            name="Other",
            domain="sensor",
            device_id="other",
            state="idle",
            attribute_names=[],
        ),
    ]
    context = build_recording_context(request, descriptors)
    assert context.recipe is RecorderProfileRecipe.VACUUM_ROBOT
    assert context.entities[0].role is EntityRole.PRIMARY
    assert context.entities[1].role is EntityRole.BATTERY
    assert context.entities[2].role is EntityRole.TRACKED
    assert context.device_entities[0].role is EntityRole.AVAILABLE
    assert context.device_entities[2].role is EntityRole.DISABLED
    assert context.entities[2].translation_key == "state"
    assert context.entities[2].integration == "dreame_vacuum"
    assert context.entities[1].role == "battery"
    inventory = context.build_metadata_record()["device_entities"]
    assert [entity["entity_id"] for entity in inventory] == ["vacuum.robot", "sensor.state", "sensor.disabled"]
    assert inventory[2]["role"] == "disabled"
    assert inventory[2]["has_live_state"] is False
    assert inventory[2]["disabled_by"] == "integration"
    serialized = json.loads(json.dumps(context.build_metadata_record()))
    assert serialized["recipe"] == "vacuum_robot"
    assert [entity["role"] for entity in serialized["entities"]] == ["primary", "battery", "tracked"]
    assert [entity["role"] for entity in serialized["device_entities"]] == ["available", "available", "disabled"]


def test_recording_context_maps_generic_and_vacuum_recipes() -> None:
    generic = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose=RecorderPurpose.COMPLEX_PROFILE,
        profile_recipe=RecorderProfileRecipe.GENERIC,
        tracked_entity_ids=("switch.device", "sensor.mode"),
    )
    vacuum = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose=RecorderPurpose.COMPLEX_PROFILE,
        profile_recipe=RecorderProfileRecipe.VACUUM_ROBOT,
        vacuum_entity_id="vacuum.robot",
        battery_entity_id="sensor.robot_battery",
    )

    assert build_recording_context(generic).device_type == "generic_iot"
    assert build_recording_context(generic).recipe is RecorderProfileRecipe.GENERIC
    assert generic.generate_model_json is False
    vacuum_context = build_recording_context(vacuum)
    assert vacuum_context.device_type == "vacuum_robot"
    assert [entity.role for entity in vacuum_context.entities] == ["primary", "battery"]

    playbook = RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec())
    with pytest.raises(ValueError, match="complex-profile"):
        build_recording_context(playbook)


def test_vacuum_context_inventories_related_dock_devices() -> None:
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id="vacuum.robot",
        battery_entity_id="sensor.battery",
        additional_entity_ids=("switch.dock_mop_drying",),
    )
    descriptors = [
        EntityDescriptor(
            entity_id="vacuum.robot",
            name="Robot",
            domain="vacuum",
            device_id="robot",
            state="docked",
            attribute_names=[],
        ),
        EntityDescriptor(
            entity_id="switch.dock_mop_drying",
            name="Drying",
            domain="switch",
            device_id="dock",
            state="off",
            attribute_names=[],
            translation_key="mop_drying",
        ),
        EntityDescriptor(
            entity_id="switch.dock_child_lock",
            name="Child lock",
            domain="switch",
            device_id="dock",
            state="off",
            attribute_names=[],
            translation_key="child_lock",
        ),
        EntityDescriptor(
            entity_id="sensor.unrelated",
            name="Other",
            domain="sensor",
            device_id="other",
            state="idle",
            attribute_names=[],
        ),
    ]

    context = build_recording_context(request, descriptors, {"robot": ["dock"], "other": ["robot"]})

    assert context.related_device_ids == ["dock"]
    record = context.build_metadata_record()
    assert record["related_device_ids"] == ["dock"]
    assert [entity["entity_id"] for entity in record["device_entities"]] == [
        "vacuum.robot",
        "switch.dock_mop_drying",
        "switch.dock_child_lock",
    ]
    assert "related_device_ids" not in build_recording_context(request, descriptors).build_metadata_record()
