from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_DOMAIN
from homeassistant.helpers.entity_registry import RegistryEntry

from custom_components.powercalc.group_include.filter import (
    CompositeFilter,
    DomainFilter,
    FilterOperator,
    NullFilter,
    create_filter,
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


async def test_domain_filter() -> None:
    registry_entry = _create_registry_entry()
    entity_filter = DomainFilter("switch")
    assert entity_filter.is_valid(registry_entry) is True

    entity_filter = DomainFilter("light")
    assert entity_filter.is_valid(registry_entry) is False


async def test_domain_filter_multiple() -> None:
    entity_filter = create_filter({CONF_DOMAIN: ["switch", "light"]})
    assert entity_filter.is_valid(_create_registry_entry()) is True


async def test_null_filter() -> None:
    assert NullFilter().is_valid(_create_registry_entry()) is True


def _create_registry_entry() -> RegistryEntry:
    return RegistryEntry(entity_id="switch.test", unique_id="abc", platform="test")
