import json
from pathlib import Path

from measure.profile.specifications import device_spec_fields


def test_device_spec_fields_follow_model_schema_device_type_conditions() -> None:
    schema_path = Path(__file__).parents[3] / "profile_library" / "model_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    fields = device_spec_fields(schema)

    light = {field.name: field for field in fields["light"]}
    assert list(light) == ["rated_power", "connectivity", "socket", "form_factor", "lumens"]
    assert light["connectivity"].collection == "array"
    assert "zigbee" in light["connectivity"].options
    assert light["socket"].collection == "scalar_or_array"
    assert "GU10" in light["socket"].options
    assert light["lumens"].value_type == "number"

    smart_switch = {field.name: field for field in fields["smart_switch"]}
    assert list(smart_switch) == ["rated_power", "connectivity", "form_factor", "max_load_watts", "power_monitoring"]
    assert smart_switch["power_monitoring"].value_type == "boolean"

    assert [field.name for field in fields["generic_iot"]] == ["rated_power", "connectivity"]
    assert "lumens" not in {field.name for field in fields["fan"]}


def test_device_spec_fields_returns_empty_catalog_for_unusable_schema() -> None:
    assert device_spec_fields({}) == {}
