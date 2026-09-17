import json

from measure.home_assistant.entities import EntityDescriptor
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.recording.context import recording_context_for
from measure.recording.models import EntityRole
from measure.request import RecorderMeasurementRequest, RecorderProfileRecipe, RecorderPurpose
import pytest


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
    context = recording_context_for(request, descriptors)
    assert context.entities[0].role is EntityRole.PRIMARY
    assert context.entities[1].role is EntityRole.BATTERY
    assert context.entities[2].role is EntityRole.TRACKED
    assert context.device_entities[0].role is EntityRole.AVAILABLE
    assert context.device_entities[2].role is EntityRole.DISABLED
    assert context.entities[2].translation_key == "state"
    assert context.entities[2].integration == "dreame_vacuum"
    assert context.entities[1].role == "battery"
    inventory = context.metadata_record()["device_entities"]
    assert [entity["entity_id"] for entity in inventory] == ["vacuum.robot", "sensor.state", "sensor.disabled"]
    assert inventory[2]["role"] == "disabled"
    assert inventory[2]["has_live_state"] is False
    assert inventory[2]["disabled_by"] == "integration"
    serialized = json.loads(json.dumps(context.metadata_record()))
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

    assert recording_context_for(generic).device_type == "generic_iot"
    assert generic.generate_model_json is False
    vacuum_context = recording_context_for(vacuum)
    assert vacuum_context.device_type == "vacuum_robot"
    assert [entity.role for entity in vacuum_context.entities] == ["primary", "battery"]

    playbook = RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec())
    with pytest.raises(ValueError, match="complex-profile"):
        recording_context_for(playbook)
