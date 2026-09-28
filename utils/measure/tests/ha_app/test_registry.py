from measure.const import MEASURE_TYPE_LABELS, MeasureType, parse_measure_type
from measure.ha_app.registry import MEASUREMENT_REGISTRY
from measure.start import MEASUREMENT_STARTS


def test_registry_contains_every_stable_measurement_kind() -> None:
    assert set(MEASUREMENT_REGISTRY) == set(MeasureType)
    assert set(MEASUREMENT_STARTS) == set(MeasureType)
    assert {kind.value for kind in MeasureType} == {
        "light",
        "speaker",
        "recorder",
        "average",
        "charging",
        "fan",
        "smart_switch",
    }


def test_registry_keeps_labels_separate_from_stable_ids() -> None:
    assert MEASURE_TYPE_LABELS[MeasureType.LIGHT] == "Light bulb(s)"
    assert parse_measure_type("Light bulb(s)") == MeasureType.LIGHT
    assert parse_measure_type("light") == MeasureType.LIGHT


def test_registry_form_fields_use_wire_request_names() -> None:
    fields = {kind: {field.name for field in definition.fields} for kind, definition in MEASUREMENT_REGISTRY.items()}

    assert "power_entity_id" in fields[MeasureType.AVERAGE]
    assert "media_player_entity_id" in fields[MeasureType.SPEAKER]
    assert "charging_entity_id" in fields[MeasureType.CHARGING]
    assert "fan_entity_id" in fields[MeasureType.FAN]
    assert all("entity_id" not in names and "powermeter_entity_id" not in names for names in fields.values())


def test_charging_definition_discovers_vacuum_domain() -> None:
    entity = next(
        field for field in MEASUREMENT_REGISTRY[MeasureType.CHARGING].fields if field.name == "charging_entity_id"
    )

    assert entity.entity_domains == ("vacuum",)


def test_light_definition_allows_multiple_entities_and_explains_the_physical_count() -> None:
    fields = {field.name: field for field in MEASUREMENT_REGISTRY[MeasureType.LIGHT].fields}

    assert fields["light_entity_id"].multiple is True
    assert fields["light_entity_id"].multiple_toggle is True
    assert "physical lights" in fields["multiple_light_count"].hint


def test_smart_switch_definition_controls_multi_selection_and_virtual_device_availability() -> None:
    definition = MEASUREMENT_REGISTRY[MeasureType.SMART_SWITCH]
    fields = {field.name: field for field in definition.fields}

    assert fields["switch_entity_id"].multiple is True
    assert fields["switch_entity_id"].multiple_toggle is False
    assert fields["power_monitoring"].control.value == "boolean"
    assert definition.supports_dummy_controller is False


def test_light_product_name_example_does_not_repeat_the_manufacturer() -> None:
    assert MEASUREMENT_REGISTRY[MeasureType.LIGHT].product_name_example == "Hue White Ambiance A60 E27"


def test_recorder_definition_starts_with_purpose_and_declares_vacuum_relationships() -> None:
    fields = {field.name: field for field in MEASUREMENT_REGISTRY[MeasureType.RECORDER].fields}

    assert "export_filename" not in fields
    assert [option.value for option in fields["recorder_purpose"].options] == ["playbook", "complex_profile"]
    complex_profile = fields["recorder_purpose"].options[1]
    assert "experimental" in complex_profile.label
    assert "activity-based composite profiles" in (complex_profile.description or "")
    assert "two independent episodes" in (complex_profile.description or "")
    assert "can create a fixed" in (complex_profile.description or "")
    assert "battery charging calibration" in (complex_profile.description or "")
    assert "at least five samples" in (complex_profile.description or "")
    assert [option.value for option in fields["profile_recipe"].options] == ["generic", "vacuum_robot"]
    profile_device_types = [option.value for option in fields["profile_device_type"].options]
    assert profile_device_types == [
        "air_purifier",
        "camera",
        "fan",
        "heating",
        "printer",
        "set_top_box",
    ]
    assert fields["profile_device_type"].default in profile_device_types
    assert fields["primary_entity_id"].narrowed_by == "profile_device_type"
    options = {option.value: option for option in fields["profile_device_type"].options}
    assert options["camera"].entity_domains == ("camera",)
    assert fields["tracked_entity_ids"].multiple is True
    assert fields["battery_entity_id"].related_to == "vacuum_entity_id"
    assert fields["battery_entity_id"].same_device_only is True
    assert "suggested dock or activity entities" in (fields["profile_recipe"].options[1].description or "")
    assert "Select every entity" in fields["profile_recipe"].options[1].guidance[1]
    assert "selected automatically" in (fields["additional_entity_ids"].hint or "")
