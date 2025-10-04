import json
from collections.abc import Callable
from decimal import Decimal
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.template import Template

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import DUMMY_ENTITY_ID, CalculationStrategy
from custom_components.powercalc.helpers import (
    collect_placeholders,
    evaluate_power,
    get_or_create_unique_id,
    get_related_entity_by_device_class,
    make_hashable,
)
from tests.common import get_test_config_dir


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
    from unittest.mock import MagicMock

    entity = MagicMock()
    entity.entity_id = "light.test"
    entity.device_id = None

    result = get_related_entity_by_device_class(hass, entity, SensorDeviceClass.BATTERY)

    assert result is None
    assert "Entity light.test has no device_id, cannot find related entity" in caplog.text


@pytest.mark.parametrize(
    "file_path,expected_placeholders",
    [
        ("powercalc/profiles/test/custom_fields/model.json", {"some_entity"}),
        ("powercalc_profiles/custom_fields_template/model.json", {"num_switches"}),
        ("powercalc_profiles/device_class_variable/model.json", {"entity:temperature"}),
        ("powercalc_profiles/download/model.json", {"entity"}),
    ],
)
def test_collect_placeholder(file_path: str, expected_placeholders: set[str]) -> None:
    with open(get_test_config_dir(file_path), encoding="utf-8") as f:
        json_data = json.loads(f.read())
    found = collect_placeholders(json_data)
    assert found == expected_placeholders
