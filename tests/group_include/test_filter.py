from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import RegistryEntry

from custom_components.powercalc.const import CONF_AND, CONF_OR, CONF_WILDCARD
from custom_components.powercalc.group_include.filter import (
    CompositeFilter,
    DomainFilter,
    FilterOperator,
    NullFilter,
    WildcardFilter,
    create_composite_filter,
)


@pytest.mark.parametrize(
    "filter_return_values,operator,expected_result",
    [
        ([True, False], FilterOperator.AND, False),
        ([False, False], FilterOperator.AND, False),
        ([True, True], FilterOperator.AND, True),
        ([True, False], FilterOperator.OR, True),
        ([False, False], FilterOperator.OR, False),
    ],
)
async def test_composite_filter(
    filter_return_values: list,
    operator: FilterOperator,
    expected_result: bool,
) -> None:
    filter_mocks = []
    for value in filter_return_values:
        entity_filter = NullFilter()
        entity_filter.is_valid = MagicMock(return_value=value)
        filter_mocks.append(entity_filter)

    registry_entry = _create_registry_entry()
    assert (
        CompositeFilter(filter_mocks, operator).is_valid(registry_entry)
        == expected_result
    )

@pytest.mark.parametrize(
    "domain,expected_result",
    [
        ("switch", True),
        ("light", False),
        (["switch", "light"], True),
    ],
)
async def test_domain_filter(domain: str | list, expected_result: bool) -> None:
    assert DomainFilter(domain).is_valid(_create_registry_entry()) is expected_result

@pytest.mark.parametrize(
    "pattern,expected_result",
    [
        ("switch.*", True),
        ("sensor.*", False),
        ("switch.t?st", True),
        ("switch.t??st", False),
    ],
)
async def test_wildcard_filter(pattern: str, expected_result: bool) -> None:
    assert WildcardFilter(pattern).is_valid(_create_registry_entry()) == expected_result


async def test_null_filter() -> None:
    assert NullFilter().is_valid(_create_registry_entry()) is True

async def test_complex_nested_filters(hass: HomeAssistant) -> None:
    entity_filter = create_composite_filter(
        {
            CONF_DOMAIN: "switch",
            CONF_OR: [
                { CONF_WILDCARD: "switch.humidifier" },
                { CONF_WILDCARD: "switch.tv" },
                { CONF_AND: [
                    { CONF_WILDCARD: "switch.some?" },
                    { CONF_WILDCARD: "switch.other?" },
                ]},
            ],
        },
        hass,
        FilterOperator.AND,
    )
    assert entity_filter.is_valid(_create_registry_entry("switch.humidifier"))
    assert not entity_filter.is_valid(_create_registry_entry("switch.humidifier2"))
    assert not entity_filter.is_valid(_create_registry_entry("switch.some1"))

def _create_registry_entry(entity_id: str = "switch.test") -> RegistryEntry:
    return RegistryEntry(entity_id=entity_id, unique_id="abc", platform="test")
