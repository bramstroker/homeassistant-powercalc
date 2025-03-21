from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_DOMAIN, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.entity_registry import RegistryEntry

from custom_components.powercalc.const import CONF_AND, CONF_AREA, CONF_FILTER, CONF_OR, CONF_WILDCARD
from custom_components.powercalc.group_include.filter import (
    AreaFilter,
    CategoryFilter,
    CompositeFilter,
    DeviceFilter,
    DomainFilter,
    FilterOperator,
    LabelFilter,
    LambdaFilter,
    NotFilter,
    NullFilter,
    WildcardFilter,
    create_composite_filter,
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
    assert CompositeFilter(filter_mocks, operator).is_valid(registry_entry) == expected_result


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


@pytest.mark.parametrize(
    "label,expected_result",
    [
        ("test", True),
        ("test2", False),
    ],
)
async def test_label_filter(label: str, expected_result: bool) -> None:
    entry = RegistryEntry(entity_id="sensor.test", unique_id="abc", platform="test", labels=["test"])
    assert LabelFilter(label).is_valid(entry) == expected_result


@pytest.mark.parametrize(
    "device,expected_result",
    [
        ("my-device", True),
        ("other-device", False),
        ({"my-device", "other-device"}, True),
        ({"my-device2", "other-device"}, False),
    ],
)
async def test_device_filter(device: str | set[str], expected_result: bool) -> None:
    assert DeviceFilter(device).is_valid(_create_registry_entry()) == expected_result


async def test_null_filter() -> None:
    assert NullFilter().is_valid(_create_registry_entry()) is True


@pytest.mark.parametrize(
    "category,filter_categories,expected_result",
    [
        (EntityCategory.DIAGNOSTIC, [EntityCategory.DIAGNOSTIC], True),
        (EntityCategory.DIAGNOSTIC, [EntityCategory.CONFIG], False),
    ],
)
async def test_category_filter(category: EntityCategory, filter_categories: list[EntityCategory], expected_result: bool) -> None:
    entry = RegistryEntry(entity_id="sensor.test", unique_id="abc", platform="test", entity_category=category)
    assert CategoryFilter(filter_categories).is_valid(entry) == expected_result


async def test_lambda_filter() -> None:
    entity_filter = LambdaFilter(lambda entity: entity.entity_id == "sensor.test")

    entry = RegistryEntry(entity_id="sensor.test", unique_id="abc", platform="test")
    assert entity_filter.is_valid(entry) is True

    entry = RegistryEntry(entity_id="sensor.test2", unique_id="abc", platform="test")
    assert entity_filter.is_valid(entry) is False


async def test_not_filter() -> None:
    assert NotFilter(NullFilter()).is_valid(_create_registry_entry()) is False


@pytest.mark.parametrize(
    "filter_type,filter_config,expected_type",
    [
        ("unknown", {}, NullFilter),
        ("domain", {}, DomainFilter),
    ],
)
async def test_create_filter(hass: HomeAssistant, filter_type: str, filter_config: dict, expected_type: type) -> None:
    filter_instance = create_filter(filter_type, filter_config, hass)
    assert isinstance(filter_instance, expected_type)


async def test_create_composite_filter(hass: HomeAssistant) -> None:
    entity_filter = create_composite_filter(
        {
            CONF_DOMAIN: "switch",
            CONF_OR: [
                {CONF_WILDCARD: "switch.humidifier"},
                {CONF_WILDCARD: "switch.tv"},
                {
                    CONF_AND: [
                        {CONF_WILDCARD: "switch.some?"},
                        {CONF_WILDCARD: "switch.other?"},
                    ],
                },
            ],
        },
        hass,
        FilterOperator.AND,
    )
    assert entity_filter.is_valid(_create_registry_entry("switch.humidifier"))
    assert not entity_filter.is_valid(_create_registry_entry("switch.humidifier2"))
    assert not entity_filter.is_valid(_create_registry_entry("switch.some1"))


async def test_create_composite_filter2(hass: HomeAssistant, area_registry: AreaRegistry) -> None:
    area_registry.async_get_or_create("kitchen")
    entity_filter = create_composite_filter(
        {
            CONF_AREA: "kitchen",
            CONF_FILTER: {
                CONF_DOMAIN: "light",
            },
        },
        hass,
        FilterOperator.AND,
    )
    assert isinstance(entity_filter, CompositeFilter)
    assert len(entity_filter.filters) == 2
    assert isinstance(entity_filter.filters[0], AreaFilter)
    assert isinstance(entity_filter.filters[1], DomainFilter)


def _create_registry_entry(entity_id: str = "switch.test") -> RegistryEntry:
    return RegistryEntry(entity_id=entity_id, unique_id="abc", platform="test", device_id="my-device")
