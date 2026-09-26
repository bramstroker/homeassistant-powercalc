from collections.abc import Callable
from decimal import Decimal
import json
from unittest.mock import PropertyMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
from homeassistant.helpers.template import Template
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import DUMMY_ENTITY_ID, PLACEHOLDER_ENTITY_BY_DEVICE_CLASS, CalculationStrategy
from custom_components.powercalc.helpers import (
    build_related_entity_placeholder_not_found_message,
    collect_placeholders,
    get_or_create_unique_id,
    get_related_entity_by_device_class,
    get_related_entity_by_translation_key,
    make_hashable,
    replace_placeholders,
    resolve_related_entity_placeholder,
)
from custom_components.powercalc.unit import evaluate_to_decimal
from tests.common import (
    build_device_entry,
    get_test_profile_dir,
    mock_devices,
    mock_entities_in_registry,
    requires_child_devices,
)


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
def test_evaluate_to_decimal(
    hass: HomeAssistant,
    power_factory: Callable[[HomeAssistant], Template | Decimal | float],
    expected_output: Decimal | None,
) -> None:
    power = power_factory(hass)
    assert evaluate_to_decimal(power) == expected_output


@patch("homeassistant.helpers.template.Template.async_render", side_effect=TemplateError(Exception()))
def test_evaluate_to_decimal_template_error(
    mock_async_render: object,
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    power = Template("{{ 1 + 3 }}", hass)
    evaluate_to_decimal(power)
    assert "Could not render template" in caplog.text


def test_get_unique_id_from_config() -> None:
    config = {CONF_UNIQUE_ID: "1234"}
    assert get_or_create_unique_id(config, SourceEntity("test", "light.test", "light"), None) == "1234"


def test_get_unique_id_generated() -> None:
    unique_id = get_or_create_unique_id({}, SourceEntity("dummy", DUMMY_ENTITY_ID, "sensor"), None)
    assert len(unique_id) == 36


def test_wled_unique_id() -> None:
    """Device id should be used as unique id for wled strategy."""
    with patch("custom_components.powercalc.power_profile.power_profile.PowerProfile") as power_profile_mock:
        mock_instance = power_profile_mock.return_value
        type(mock_instance).calculation_strategy = PropertyMock(return_value=CalculationStrategy.WLED)

        device_entry = build_device_entry(config_entry_id="test", id="123456")
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
def test_make_hashable(value: set | list | dict, output: tuple | frozenset) -> None:
    assert make_hashable(value) == output


def test_get_related_entity_by_device_class_no_device_id(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test get_related_entity_by_device_class when entity has no device_id."""
    entity = SourceEntity("test", "light.test", "light")

    result = get_related_entity_by_device_class(hass, entity, SensorDeviceClass.BATTERY)

    assert result is None
    assert "No device_id available, cannot find related entity" in caplog.text


def test_get_related_entity_by_translation_key(hass: HomeAssistant) -> None:
    mock_entities_in_registry(
        hass,
        {
            "sensor.test_power": {"platform": "test", "device_id": "device_1", "translation_key": "power"},
            "sensor.test_energy": {"platform": "test", "device_id": "device_1", "translation_key": "energy"},
        },
    )

    source_entity = SourceEntity(
        "test",
        "light.test",
        "light",
        device_entry=build_device_entry(config_entry_id="test", id="device_1"),
    )
    result = get_related_entity_by_translation_key(hass, source_entity, "power")

    assert result == "sensor.test_power"


@pytest.fixture(params=["entity_by_translation_key:power", "entity_by_device_class:power"])
def related_placeholder(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.mark.parametrize("own_matches", [0, 1, 2])
def test_related_entity_prefers_source_device(
    hass: HomeAssistant,
    related_placeholder: str,
    own_matches: int,
) -> None:
    devices = mock_devices(
        hass,
        {
            "robot": {"identifiers": {("roborock", "robot")}},
            "dock": {"identifiers": {("roborock", "robot_dock")}},
        },
    )
    matching_attributes = {"translation_key": "power", "original_device_class": SensorDeviceClass.POWER}
    entities = {"sensor.dock_power": {"device_id": "dock", **matching_attributes}}
    for index in range(own_matches):
        entities[f"sensor.robot_power_{index}"] = {"device_id": "robot", **matching_attributes}
    mock_entities_in_registry(hass, entities)
    source = SourceEntity("robot", "vacuum.robot", "vacuum", device_entry=devices["robot"])

    result = resolve_related_entity_placeholder(hass, related_placeholder, source)

    assert result == ("sensor.robot_power_0" if own_matches else "sensor.dock_power")


@pytest.mark.parametrize("disabled", [False, True])
def test_related_entity_only_searches_the_matching_roborock_dock(
    hass: HomeAssistant,
    related_placeholder: str,
    disabled: bool,
) -> None:
    devices = mock_devices(
        hass,
        {
            "robot": {"identifiers": {("roborock", "robot")}},
            "other_robot": {"identifiers": {("roborock", "other_robot")}},
            "other_dock": {"identifiers": {("roborock", "other_robot_dock")}},
            "wrong_namespace": {"identifiers": {("other", "robot_dock")}},
            "wrong_entry": {"identifiers": {("roborock", "robot_dock")}, "config_entry_id": "other"},
            "unrelated": {},
            "via_device": {"via_device_id": "robot"},
            "dock": {"identifiers": {("roborock", "robot_dock")}},
        },
    )
    entities = {}
    for device_id in devices:
        if device_id == "robot":
            continue
        entities[f"sensor.{device_id}_power"] = {
            "device_id": device_id,
            "translation_key": "power",
            "original_device_class": SensorDeviceClass.POWER,
            "disabled_by": RegistryEntryDisabler.USER if disabled and device_id == "dock" else None,
        }
    mock_entities_in_registry(hass, entities)
    source = SourceEntity("robot", "vacuum.robot", "vacuum", device_entry=devices["robot"])

    result = resolve_related_entity_placeholder(hass, related_placeholder, source)

    assert result == (None if disabled else "sensor.dock_power")
    other_source = SourceEntity("other_robot", "vacuum.other_robot", "vacuum", device_entry=devices["other_robot"])
    assert resolve_related_entity_placeholder(hass, related_placeholder, other_source) == "sensor.other_robot_power"


def test_related_entity_skips_disabled_source_match(
    hass: HomeAssistant,
    related_placeholder: str,
) -> None:
    devices = mock_devices(
        hass,
        {
            "robot": {"identifiers": {("roborock", "robot")}},
            "dock": {"identifiers": {("roborock", "robot_dock")}},
        },
    )
    mock_entities_in_registry(
        hass,
        {
            "sensor.robot_power": {
                "device_id": "robot",
                "translation_key": "power",
                "original_device_class": SensorDeviceClass.POWER,
                "disabled_by": RegistryEntryDisabler.USER,
            },
            "sensor.dock_power": {
                "device_id": "dock",
                "translation_key": "power",
                "original_device_class": SensorDeviceClass.POWER,
            },
            "sensor.dock_temperature": {"device_id": "dock", "translation_key": "temperature"},
        },
    )
    source = SourceEntity("robot", "vacuum.robot", "vacuum", device_entry=devices["robot"])

    assert resolve_related_entity_placeholder(hass, related_placeholder, source) == "sensor.dock_power"


@requires_child_devices
@pytest.mark.parametrize("matching_children", [0, 1, 2])
def test_related_entity_resolves_native_children_without_ambiguity(
    hass: HomeAssistant,
    device_registry: DeviceRegistry,
    related_placeholder: str,
    matching_children: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)
    parent = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("test", "parent")},
    )
    entities = {}
    for index in range(matching_children):
        child = device_registry.async_get_or_create_child(
            config_entry_id=config_entry.entry_id,
            parent_device_id=parent.id,
            identifiers={("test", f"child_{index}")},
        )
        entities[f"sensor.child_{index}_power"] = {
            "device_id": child.id,
            "translation_key": "power",
            "original_device_class": SensorDeviceClass.POWER,
        }
    mock_entities_in_registry(hass, entities)
    source = SourceEntity("parent", "switch.parent", "switch", device_entry=parent)

    result = resolve_related_entity_placeholder(hass, related_placeholder, source)

    assert result == ("sensor.child_0_power" if matching_children == 1 else None)
    if matching_children == 2:
        assert "Ambiguous related entities for switch.parent" in caplog.text
        assert "power" in caplog.text
        assert "sensor.child_0_power, sensor.child_1_power" in caplog.text


def test_related_entity_rejects_multiple_matches_on_one_dock(
    hass: HomeAssistant,
    related_placeholder: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    devices = mock_devices(
        hass,
        {
            "robot": {"identifiers": {("roborock", "robot")}},
            "dock": {"identifiers": {("roborock", "robot_dock")}},
        },
    )
    mock_entities_in_registry(
        hass,
        {
            f"sensor.dock_power_{index}": {
                "device_id": "dock",
                "translation_key": "power",
                "original_device_class": SensorDeviceClass.POWER,
            }
            for index in range(2)
        },
    )
    source = SourceEntity("robot", "vacuum.robot", "vacuum", device_entry=devices["robot"])

    assert resolve_related_entity_placeholder(hass, related_placeholder, source) is None
    assert "sensor.dock_power_0, sensor.dock_power_1" in caplog.text


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
    mock_entities_in_registry(
        hass,
        {
            "sensor.test_battery": {
                "platform": "test",
                "device_id": "device_1",
                "device_class": SensorDeviceClass.BATTERY,
            },
        },
    )

    assert not resolve_related_entity_placeholder(
        hass,
        f"{PLACEHOLDER_ENTITY_BY_DEVICE_CLASS}foo",
        SourceEntity(
            "test",
            "light.test",
            "light",
            device_entry=build_device_entry(config_entry_id="test", id="device_1"),
        ),
    )


def test_resolve_related_entity_placeholder_unknown_placeholder(hass: HomeAssistant) -> None:
    assert not resolve_related_entity_placeholder(
        hass,
        "whatever",
        SourceEntity(
            "test",
            "light.test",
            "light",
            device_entry=build_device_entry(config_entry_id="test", id="device_1"),
        ),
    )


def test_build_related_entity_placeholder_not_found_message_unknown_placeholder() -> None:
    assert (
        build_related_entity_placeholder_not_found_message("whatever", "light.test")
        == "Could not find related entity for placeholder whatever of entity light.test"
    )
