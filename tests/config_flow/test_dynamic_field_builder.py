from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import EntitySelector, NumberSelector
import pytest
import voluptuous as vol

from custom_components.powercalc.common import SourceEntity, create_source_entity
from custom_components.powercalc.flow_helper.dynamic_field_builder import build_dynamic_field_schema
from custom_components.powercalc.power_profile.power_profile import PowerProfile
from tests.common import mock_device, mock_entities_in_registry


@pytest.mark.parametrize(
    "auto_select",
    [
        {"integration": "tapo_control", "unique_id_pattern": r"-floodlight\(timed\)$"},
        {"translation_key": "floodlight"},
        {"translation_key": "floodlight", "unique_id_pattern": r"-floodlight\(timed\)$"},
    ],
)
def test_auto_select_renamed_entity(hass: HomeAssistant, auto_select: dict[str, str]) -> None:
    device = mock_device(hass)
    mock_entities_in_registry(
        hass,
        {
            "light.my_renamed_spotlight": {
                "device_id": device.id,
                "platform": "tapo_control",
                "unique_id": "aa:bb-camera-floodlight(timed)",
                "translation_key": "floodlight",
            },
            "light.other_camera": {"device_id": "other-device", "translation_key": "floodlight"},
            "light.disabled": {
                "device_id": device.id,
                "platform": "tapo_control",
                "unique_id": "disabled-floodlight(timed)",
                "translation_key": "floodlight",
                "disabled_by": er.RegistryEntryDisabler.USER,
            },
        },
    )
    profile = create_power_profile(
        hass,
        {"spotlight": {"label": "Spotlight", "selector": {"entity": {"domain": "light"}}, "auto_select": auto_select}},
    )
    source = SourceEntity("sensor.dummy", "Camera", "sensor", device_entry=device)
    schema = build_dynamic_field_schema(hass, profile, source)

    assert schema({}) == {"spotlight": "light.my_renamed_spotlight"}
    assert "include_entities" not in profile.custom_fields[0].selector["entity"]


@pytest.mark.parametrize(
    "entity_config,entity_attributes,expected",
    [
        ({"domain": "light"}, {}, "light.spotlight"),
        ({"domain": "switch"}, {}, None),
        ({"integration": "other"}, {}, None),
        ({"device_class": "outlet"}, {"original_device_class": "outlet"}, "light.spotlight"),
        ({"device_class": "outlet"}, {"device_class": "switch", "original_device_class": "outlet"}, None),
        ({"device_class": "outlet"}, {}, None),
        ({"include_entities": ["light.other"]}, {}, None),
        ({"include_entities": []}, {}, None),
        ({"exclude_entities": ["light.spotlight"]}, {}, None),
        ({"filter": {"domain": "light", "integration": "tapo_control"}}, {}, "light.spotlight"),
        ({"filter": [{"domain": "switch"}, {"domain": "light"}]}, {}, "light.spotlight"),
        ({"filter": {"domain": "switch"}}, {}, None),
        ({"domain": "switch", "filter": {"domain": "light"}}, {}, None),
        ({"filter": []}, {}, None),
        ({"filter": {"supported_features": ["light.LightEntityFeature.EFFECT"]}}, {}, None),
        ({}, {"translation_key": "different"}, None),
    ],
)
def test_auto_select_respects_selector_filters(
    hass: HomeAssistant,
    entity_config: dict[str, Any],
    entity_attributes: dict[str, Any],
    expected: str | None,
) -> None:
    device = mock_device(hass)
    mock_entities_in_registry(
        hass,
        {
            "light.spotlight": {
                "device_id": device.id,
                "platform": "tapo_control",
                "translation_key": "floodlight",
                **entity_attributes,
            }
        },
    )
    profile = create_power_profile(
        hass,
        {
            "spotlight": {
                "label": "Spotlight",
                "selector": {"entity": entity_config},
                "auto_select": {"translation_key": "floodlight"},
            }
        },
    )
    schema = build_dynamic_field_schema(
        hass, profile, SourceEntity("sensor.dummy", "Camera", "sensor", device_entry=device)
    )
    field = next(iter(schema.schema))
    if expected is None:
        assert field.default is vol.UNDEFINED
    else:
        assert field.default() == expected


@pytest.mark.parametrize("candidate_count", [0, 2])
def test_auto_select_requires_one_match(hass: HomeAssistant, candidate_count: int) -> None:
    device = mock_device(hass)
    mock_entities_in_registry(
        hass,
        {
            f"light.spotlight_{index}": {"device_id": device.id, "translation_key": "floodlight"}
            for index in range(candidate_count)
        },
    )
    profile = create_power_profile(
        hass,
        {
            "spotlight": {
                "label": "Spotlight",
                "selector": {"entity": {}},
                "auto_select": {"translation_key": "floodlight"},
            }
        },
    )
    schema = build_dynamic_field_schema(
        hass, profile, SourceEntity("sensor.dummy", "Camera", "sensor", device_entry=device)
    )
    with pytest.raises(vol.MultipleInvalid, match="required key not provided"):
        schema({})


@pytest.mark.parametrize("has_source", [False, True])
def test_auto_select_without_device(hass: HomeAssistant, has_source: bool) -> None:
    profile = create_power_profile(
        hass,
        {
            "spotlight": {
                "label": "Spotlight",
                "selector": {"entity": {}},
                "auto_select": {"translation_key": "floodlight"},
            }
        },
    )
    source = SourceEntity("sensor.test", "Test", "sensor") if has_source else None
    schema = build_dynamic_field_schema(hass, profile, source)
    assert next(iter(schema.schema)).default is vol.UNDEFINED


@pytest.mark.parametrize(
    "pattern,matches",
    [
        (r"-floodlight\(timed\)$", True),
        ("^aa:bb-", True),
        (r"^aa:bb-camera-floodlight\(timed\)$", True),
        ("camera", True),
        ("^camera", False),
        ("camera$", False),
        (r"^floodlight\(timed\)$", False),
        ("-different$", False),
        ("FLOODLIGHT", False),
    ],
)
def test_auto_select_unique_id_pattern(hass: HomeAssistant, pattern: str, matches: bool) -> None:
    device = mock_device(hass)
    mock_entities_in_registry(
        hass,
        {"light.spotlight": {"device_id": device.id, "unique_id": "aa:bb-camera-floodlight(timed)"}},
    )
    profile = create_power_profile(
        hass,
        {
            "spotlight": {
                "label": "Spotlight",
                "selector": {"entity": {}},
                "auto_select": {"unique_id_pattern": pattern},
            },
        },
    )
    schema = build_dynamic_field_schema(
        hass, profile, SourceEntity("sensor.dummy", "Camera", "sensor", device_entry=device)
    )
    if matches:
        assert schema({}) == {"spotlight": "light.spotlight"}
    else:
        assert next(iter(schema.schema)).default is vol.UNDEFINED


def test_explicit_default_and_user_selection_override_auto_select(hass: HomeAssistant) -> None:
    device = mock_device(hass)
    mock_entities_in_registry(
        hass,
        {
            "light.spotlight": {"device_id": device.id, "translation_key": "floodlight"},
            "light.manual": {"device_id": device.id},
        },
    )
    profile = create_power_profile(
        hass,
        {
            "spotlight": {
                "label": "Spotlight",
                "default": "light.manual",
                "selector": {"entity": {}},
                "auto_select": {"translation_key": "floodlight"},
            }
        },
    )
    source = SourceEntity("sensor.dummy", "Camera", "sensor", device_entry=device)
    schema = build_dynamic_field_schema(hass, profile, source)
    assert schema({}) == {"spotlight": "light.manual"}
    assert schema({"spotlight": "light.spotlight"}) == {"spotlight": "light.spotlight"}

    profile.json_data["fields"]["spotlight"].pop("default")
    schema = build_dynamic_field_schema(hass, profile, source)
    assert schema({}) == {"spotlight": "light.spotlight"}
    assert schema({"spotlight": "light.manual"}) == {"spotlight": "light.manual"}


def test_build_schema(hass: HomeAssistant) -> None:
    profile = create_power_profile(
        hass,
        {
            "test1": {
                "label": "Test 1",
                "description": "Test 1",
                "selector": {
                    "entity": {
                        "multiple": True,
                        "device_class": "power",
                    },
                },
            },
            "test2": {
                "label": "Test 2",
                "description": "Test 2",
                "selector": {
                    "number": {
                        "min": 0,
                        "max": 60,
                        "step": 1,
                        "unit_of_measurement": "minutes",
                        "mode": "slider",
                    },
                },
            },
        },
    )
    schema = build_dynamic_field_schema(hass, profile, SourceEntity("sensor.test", "sensor.test", "sensor"))
    assert len(schema.schema) == 2
    assert "test1" in schema.schema
    test1 = schema.schema["test1"]
    assert isinstance(test1, EntitySelector)
    assert test1.config == {"multiple": True, "device_class": ["power"], "reorder": False}

    assert "test2" in schema.schema
    test2 = schema.schema["test2"]
    assert isinstance(test2, NumberSelector)
    assert test2.config == {"min": 0, "max": 60, "step": 1, "unit_of_measurement": "minutes", "mode": "slider"}


def test_omit_description(hass: HomeAssistant) -> None:
    profile = create_power_profile(
        hass,
        {
            "test1": {
                "label": "Test 1",
                "selector": {
                    "entity": {
                        "multiple": True,
                        "device_class": "power",
                    },
                },
            },
        },
    )
    schema = build_dynamic_field_schema(hass, profile, SourceEntity("sensor.test", "sensor.test", "sensor"))

    schema_keys = list(schema.schema.keys())
    assert schema_keys[schema_keys.index("test1")].description == "Test 1"


def test_set_default_value(hass: HomeAssistant) -> None:
    profile = create_power_profile(
        hass,
        {
            "test1": {
                "label": "Test 1",
                "description": "Test 1",
                "default": 15,
                "selector": {
                    "number": {
                        "min": 0,
                        "max": 60,
                        "step": 1,
                        "unit_of_measurement": "minutes",
                        "mode": "slider",
                    },
                },
            },
        },
    )

    schema = build_dynamic_field_schema(hass, profile, SourceEntity("sensor.test", "sensor.test", "sensor"))

    schema_keys = list(schema.schema.keys())
    assert schema_keys[schema_keys.index("test1")].default() == 15


def test_entity_pick_filter_by_device(hass: HomeAssistant) -> None:
    mock_device(
        hass,
        "device_123",
        "Test Manufacturer",
        "Test Model",
        identifiers={("powercalc", "device_123")},
        name="Test Device",
    )

    mock_entities_in_registry(
        hass,
        {
            "sensor.test1": {"unique_id": "unique_test1", "platform": "test_platform", "device_id": "device_123"},
            "switch.test2": {"unique_id": "unique_test2", "platform": "test_platform", "device_id": "device_123"},
        },
    )

    profile = create_power_profile(
        hass,
        {
            "test1": {
                "label": "Test 1",
                "description": "Test 1",
                "selector": {
                    "entity": {
                        "domain": "switch",
                    },
                },
            },
        },
    )

    source_entity = create_source_entity("sensor.test1", hass)

    schema = build_dynamic_field_schema(hass, profile, source_entity)
    assert len(schema.schema) == 1
    assert "test1" in schema.schema
    test1 = schema.schema["test1"]
    assert isinstance(test1, EntitySelector)
    assert test1.config == {
        "multiple": False,
        "domain": ["switch"],
        "include_entities": ["sensor.test1", "switch.test2"],
        "reorder": False,
    }


def create_power_profile(hass: HomeAssistant, fields: dict[str, Any]) -> PowerProfile:
    return PowerProfile(
        hass,
        "test",
        "test",
        "",
        {
            "name": "test",
            "fields": fields,
        },
    )
