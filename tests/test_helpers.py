from collections.abc import Callable
from decimal import Decimal
import json
from unittest.mock import PropertyMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.template import Template
import pytest
from pytest_homeassistant_custom_component.common import RegistryEntryWithDefaults, mock_registry

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import DUMMY_ENTITY_ID, PLACEHOLDER_ENTITY_BY_DEVICE_CLASS, CalculationStrategy
from custom_components.powercalc.helpers import (
    build_related_entity_placeholder_not_found_message,
    collect_placeholders,
    evaluate_power,
    get_or_create_unique_id,
    get_related_entity_by_device_class,
    get_related_entity_by_translation_key,
    make_hashable,
    replace_placeholders,
    resolve_related_entity_placeholder,
)
from tests.common import get_test_profile_dir


@pytest.mark.parametrize(
    "power_factory,expected_output",
    [
        (lambda hass: Template("unknown", hass), None),
        (lambda hass: Template("{{ 1 + 3 | float }}", hass), Decimal("4.0")),
        (lambda hass: 20.5, Decimal("20.5")),
        (lambda hass: "foo", None),
        (lambda hass: Decimal("40.65"), Decimal("40.65")),
        (lambda hass: (1, 2), None),
    ],
)
async def test_evaluate_power(
    hass: HomeAssistant,
    power_factory: Callable[[HomeAssistant], Template | Decimal | float],
    expected_output: Decimal | None,
) -> None:
    power = power_factory(hass)
    assert await evaluate_power(power) == expected_output


@patch("homeassistant.helpers.template.Template.async_render", side_effect=TemplateError(Exception()))
async def test_evaluate_power_template_error(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    power = Template("{{ 1 + 3 }}")
    power.hass = hass
    await evaluate_power(power)
    assert "Could not render power template" in caplog.text


async def test_get_unique_id_from_config() -> None:
    config = {CONF_UNIQUE_ID: "1234"}
    assert get_or_create_unique_id(config, SourceEntity("test", "light.test", "light"), None) == "1234"


async def test_get_unique_id_generated() -> None:
    unique_id = get_or_create_unique_id({}, SourceEntity("dummy", DUMMY_ENTITY_ID, "sensor"), None)
    assert len(unique_id) == 36


async def test_wled_unique_id() -> None:
    """Device id should be used as unique id for wled strategy."""
    with patch("custom_components.powercalc.power_profile.power_profile.PowerProfile") as power_profile_mock:
        mock_instance = power_profile_mock.return_value
        type(mock_instance).calculation_strategy = PropertyMock(return_value=CalculationStrategy.WLED)

        device_entry = DeviceEntry(id="123456")
        source_entity = SourceEntity("wled", "light.wled", "light", device_entry=device_entry)
        unique_id = get_or_create_unique_id({}, source_entity, mock_instance)
        assert unique_id == "pc_123456"


@pytest.mark.parametrize(
    "value,output",
    [
        ({"a", "b", "c"}, frozenset({"a", "b", "c"})),
        (["a", "b", "c"], ("a", "b", "c")),
        ({"a": 1, "b": 2}, frozenset([("a", 1), ("b", 2)])),
    ],
)
async def test_make_hashable(value: set | list | dict, output: tuple | frozenset) -> None:
    assert make_hashable(value) == output


def test_get_related_entity_by_device_class_no_device_id(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test get_related_entity_by_device_class when entity has no device_id."""
    entity = SourceEntity("test", "light.test", "light")

    result = get_related_entity_by_device_class(hass, entity, SensorDeviceClass.BATTERY)

    assert result is None
    assert "No device_id available, cannot find related entity" in caplog.text


def test_get_related_entity_by_translation_key(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "sensor.test_power": RegistryEntryWithDefaults(
                entity_id="sensor.test_power",
                unique_id="1234",
                platform="test",
                device_id="device_1",
                translation_key="power",
            ),
            "sensor.test_energy": RegistryEntryWithDefaults(
                entity_id="sensor.test_energy",
                unique_id="5678",
                platform="test",
                device_id="device_1",
                translation_key="energy",
            ),
        },
    )

    source_entity = SourceEntity("test", "light.test", "light", device_entry=DeviceEntry(id="device_1"))
    result = get_related_entity_by_translation_key(hass, source_entity, "power")

    assert result == "sensor.test_power"


@pytest.mark.parametrize(
    "file_path,expected_placeholders",
    [
        ("custom_fields/model.json", {"some_entity"}),
        ("custom_fields_template/model.json", {"num_switches"}),
        ("device_class_variable/model.json", {"entity_by_device_class:temperature"}),
        ("download/model.json", {"entity"}),
    ],
)
def test_collect_placeholder(file_path: str, expected_placeholders: set[str]) -> None:
    with open(get_test_profile_dir(file_path), encoding="utf-8") as f:
        json_data = json.loads(f.read())
    found = collect_placeholders(json_data)
    assert found == expected_placeholders


def test_replace_placeholder() -> None:
    json_data = {
        "name": "Test [[entity_by_device_class:temperature]]",
    }
    placeholders = {"entity_by_device_class:temperature": "sensor.test"}
    replace_placeholders(json_data, placeholders)
    assert json_data["name"] == "Test sensor.test"


def test_resolve_related_entity_placeholder_no_source_entity(hass: HomeAssistant) -> None:
    assert not resolve_related_entity_placeholder(
        hass,
        f"{PLACEHOLDER_ENTITY_BY_DEVICE_CLASS}battery",
        None,
    )


def test_resolve_related_entity_placeholder_unknown_device_class(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "sensor.test_battery": RegistryEntryWithDefaults(
                entity_id="sensor.test_battery",
                unique_id="1234",
                platform="test",
                device_id="device_1",
                device_class=SensorDeviceClass.BATTERY,
            ),
        },
    )

    assert not resolve_related_entity_placeholder(
        hass,
        f"{PLACEHOLDER_ENTITY_BY_DEVICE_CLASS}foo",
        SourceEntity("test", "light.test", "light", device_entry=DeviceEntry(id="device_1")),
    )


def test_resolve_related_entity_placeholder_unknown_placeholder(hass: HomeAssistant) -> None:
    assert not resolve_related_entity_placeholder(
        hass,
        "whatever",
        SourceEntity("test", "light.test", "light", device_entry=DeviceEntry(id="device_1")),
    )


def test_build_related_entity_placeholder_not_found_message_unknown_placeholder() -> None:
    assert (
        build_related_entity_placeholder_not_found_message("whatever", "light.test")
        == "Could not find related entity for placeholder whatever of entity light.test"
    )
