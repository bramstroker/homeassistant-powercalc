from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.selector import EntitySelector, NumberSelector
from pytest_homeassistant_custom_component.common import RegistryEntryWithDefaults, mock_device_registry, mock_registry

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.flow_helper.dynamic_field_builder import build_dynamic_field_schema
from custom_components.powercalc.power_profile.power_profile import PowerProfile


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
    schema = build_dynamic_field_schema(profile)
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
    schema = build_dynamic_field_schema(profile)

    schema_keys = list(schema.schema.keys())
    assert schema_keys[schema_keys.index("test1")].description == "Test 1"


async def test_entity_pick_filter_by_device(hass: HomeAssistant) -> None:
    mock_device_registry(
        hass,
        {
            "device_123": DeviceEntry(
                id="device_123",
                config_entries=set(),
                identifiers={("powercalc", "device_123")},
                manufacturer="Test Manufacturer",
                name="Test Device",
                model="Test Model",
            ),
        },
    )

    mock_registry(
        hass,
        {
            "sensor.test1": RegistryEntryWithDefaults(
                entity_id="sensor.test1",
                unique_id="unique_test1",
                platform="test_platform",
                device_id="device_123",
            ),
            "switch.test2": RegistryEntryWithDefaults(
                entity_id="switch.test2",
                unique_id="unique_test2",
                platform="test_platform",
                device_id="device_123",
            ),
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

    source_entity = await create_source_entity("sensor.test1", hass)

    schema = build_dynamic_field_schema(hass, profile, source_entity)
    assert len(schema.schema) == 1
    assert "test1" in schema.schema
    test1 = schema.schema["test1"]
    assert isinstance(test1, EntitySelector)
    assert test1.config == {
        "multiple": False,
        "domain": ["switch"],
        "include_entities": ["sensor.test1", "switch.test2"],
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
