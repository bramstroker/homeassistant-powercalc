import json
from pathlib import Path

from measure.profile.specifications import DeviceSpecField, device_spec_fields
import pytest


def test_device_spec_fields_follow_model_schema_device_type_conditions() -> None:
    schema_path = Path(__file__).parents[4] / "profile_library" / "model_schema.json"
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


def test_device_spec_fields_resolve_references_and_preserve_local_descriptions() -> None:
    schema = {
        "$defs": {
            "power/rating~watts": {"type": "number", "description": "Default description"},
            "connection": {"type": "string", "enum": ["wifi", "zigbee"]},
        },
        "properties": {
            "device_type": {"enum": ["light"]},
            "device_specs": {
                "properties": {
                    "rated_power": {"$ref": "#/$defs/power~1rating~0watts", "description": "Power in watts"},
                    "connectivity": {"type": "array", "items": {"$ref": "#/$defs/connection"}},
                },
            },
        },
    }

    assert device_spec_fields(schema) == {
        "light": [
            DeviceSpecField("rated_power", "Rated power", "Power in watts", "number"),
            DeviceSpecField("connectivity", "Connectivity", "", "string", "array", ("wifi", "zigbee")),
        ],
    }


def test_device_spec_conditions_override_only_matching_device_types() -> None:
    schema = {
        "properties": {
            "device_type": {"enum": ["light", "fan", "smart_switch"]},
            "device_specs": {"properties": {"rated_power": {"type": "number"}}},
        },
        "allOf": [
            {
                "if": {"properties": {"device_type": {"enum": ["light", "fan", "future_device"]}}},
                "then": {
                    "properties": {
                        "device_specs": {
                            "properties": {
                                "rated_power": {"type": "integer"},
                                "speed_control": {"type": "boolean"},
                            },
                        },
                    },
                },
            },
            {
                "if": {"properties": {"device_type": {"const": "light"}}},
                "then": {"properties": {"device_specs": {"properties": {"lumens": {"type": "number"}}}}},
            },
        ],
    }

    fields = device_spec_fields(schema)

    assert [field.name for field in fields["light"]] == ["rated_power", "speed_control", "lumens"]
    assert [field.name for field in fields["fan"]] == ["rated_power", "speed_control"]
    assert fields["fan"][0].value_type == "integer"
    assert fields["smart_switch"] == [DeviceSpecField("rated_power", "Rated power", "", "number")]
    assert "future_device" not in fields


@pytest.mark.parametrize(
    "unsupported_field",
    [
        {"type": "object", "properties": {"nested": {"type": "string"}}},
        {"type": "array"},
        {"$ref": "#/$defs/missing"},
        {"oneOf": [{"type": "string"}, {"type": "number"}]},
    ],
)
def test_device_spec_fields_skip_unsupported_fields_without_losing_supported_ones(
    unsupported_field: dict[str, object],
) -> None:
    schema = {
        "properties": {
            "device_type": {"enum": ["light"]},
            "device_specs": {"properties": {"unsupported": unsupported_field, "rated_power": {"type": "number"}}},
        },
    }

    assert device_spec_fields(schema) == {"light": [DeviceSpecField("rated_power", "Rated power", "", "number")]}


def test_device_spec_fields_ignore_conditions_that_also_depend_on_other_properties() -> None:
    schema = {
        "properties": {"device_type": {"enum": ["light"]}},
        "allOf": [
            {
                "if": {"properties": {"device_type": {"const": "light"}, "calculation_strategy": {"const": "lut"}}},
                "then": {"properties": {"device_specs": {"properties": {"lumens": {"type": "number"}}}}},
            },
        ],
    }

    assert device_spec_fields(schema) == {"light": []}
