from __future__ import annotations

from measure.const import MEASURE_TYPE_LABELS, MeasureType, parse_measure_type
from measure.ha_app.registry import MEASUREMENT_REGISTRY


def test_registry_contains_every_stable_measurement_kind() -> None:
    assert set(MEASUREMENT_REGISTRY) == set(MeasureType)
    assert {kind.value for kind in MeasureType} == {"light", "speaker", "recorder", "average", "charging", "fan"}


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


def test_charging_definition_discovers_both_supported_domains() -> None:
    entity = next(
        field for field in MEASUREMENT_REGISTRY[MeasureType.CHARGING].fields if field.name == "charging_entity_id"
    )

    assert entity.entity_domains == ("vacuum", "lawn_mower")
