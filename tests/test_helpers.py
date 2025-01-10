from decimal import Decimal
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.template import Template

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import DUMMY_ENTITY_ID, CalculationStrategy
from custom_components.powercalc.helpers import evaluate_power, get_or_create_unique_id, make_hashable


@pytest.mark.parametrize(
    "power,output",
    [
        (Template("unknown"), None),
        (Template("{{ 1 + 3 | float }}"), Decimal("4.0")),
        (20.5, Decimal("20.5")),
        ("foo", None),
        (Decimal("40.65"), Decimal("40.65")),
        ((1, 2), None),
    ],
)
async def test_evaluate_power(
    hass: HomeAssistant,
    power: Template | Decimal | float,
    output: Decimal | None,
) -> None:
    if isinstance(power, Template):
        power.hass = hass
    assert await evaluate_power(power) == output


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
