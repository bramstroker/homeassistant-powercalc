from unittest.mock import MagicMock

from homeassistant.const import CONF_DOMAIN, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry, floor_registry
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
import pytest
from pytest_homeassistant_custom_component.common import RegistryEntryWithDefaults, mock_device_registry, mock_registry

from custom_components.powercalc.const import CONF_AND, CONF_AREA, CONF_FILTER, CONF_OR, CONF_WILDCARD
from custom_components.powercalc.errors import SensorConfigurationError
from custom_components.powercalc.group_include.filter import (
    AreaFilter,
    CategoryFilter,
    CompositeFilter,
    DeviceFilter,
    DomainFilter,
    FilterOperator,
    FloorFilter,
    GroupFilter,
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
        (["test"], True),
        (["test2"], False),
        (["test", "test2"], True),
        (["test2", "test3"], False),
    ],
)
async def test_label_filter(label: str | list[str], expected_result: bool) -> None:
    entry = RegistryEntryWithDefaults(entity_id="sensor.test", unique_id="abc", platform="test", labels=["test"])
    assert LabelFilter(label).is_valid(entry) == expected_result


@pytest.mark.parametrize(
    "entity_device,entity_area,floor,expected_result,expect_exception",
    [
        ("my-device", None, "first_floor", True, False),
        ("my-device", None, "First Floor", True, False),
        (None, "bathroom", "Second Floor", True, False),
        ("my_device", None, "floor2", False, True),
        # Test with list of floors
        ("my-device", None, ["first_floor", "Second Floor"], True, False),
        (None, "bathroom", ["first_floor", "Second Floor"], True, False),
        (None, "kitchen", ["Second Floor"], False, False),
        ("my_device", None, ["floor2", "another_floor"], False, True),
    ],
)
async def test_floor_filter(
    hass: HomeAssistant,
    entity_device: str | None,
    entity_area: str | None,
    floor: str | list[str],
    expected_result: bool,
    expect_exception: bool,
) -> None:
    floor_reg = floor_registry.async_get(hass)
    floor_entry1 = floor_reg.async_create("First floor")
    floor_reg = floor_registry.async_get(hass)
    floor_entry2 = floor_reg.async_create("Second floor")

    area_reg = area_registry.async_get(hass)
    area_entry1 = area_reg.async_get_or_create("Kitchen")
    area_reg.async_update(area_id=area_entry1.id, floor_id=floor_entry1.floor_id)
    area_entry2 = area_reg.async_get_or_create("Living room")
    area_reg.async_update(area_id=area_entry2.id, floor_id=floor_entry1.floor_id)
    area_entry3 = area_reg.async_get_or_create("Bathroom")
    area_reg.async_update(area_id=area_entry3.id, floor_id=floor_entry2.floor_id)
    area_entry4 = area_reg.async_get_or_create("Bedroom1")
    area_reg.async_update(area_id=area_entry4.id, floor_id=floor_entry2.floor_id)

    mock_device_registry(
        hass,
        {
            "my-device": DeviceEntry(
                id="my-device",
                name="My device",
                manufacturer="Mock",
                model="Device",
                area_id="kitchen",
            ),
        },
    )

    entry = RegistryEntryWithDefaults(
        entity_id="switch.test",
        unique_id="abc",
        platform="test",
        device_id=entity_device,
        area_id=entity_area,
    )
    if expect_exception:
        with pytest.raises(SensorConfigurationError):
            FloorFilter(hass, floor).is_valid(entry)
        return

    assert FloorFilter(hass, floor).is_valid(entry) == expected_result


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
    "category,filter_categories,expected_result,expect_exception",
    [
        # Single EntityCategory
        (EntityCategory.DIAGNOSTIC, EntityCategory.DIAGNOSTIC, True, False),
        (EntityCategory.DIAGNOSTIC, EntityCategory.CONFIG, False, False),
        # Single string category
        (EntityCategory.DIAGNOSTIC, "diagnostic", True, False),
        (EntityCategory.DIAGNOSTIC, "config", False, False),
        # List with multiple EntityCategory objects
        (EntityCategory.DIAGNOSTIC, [EntityCategory.DIAGNOSTIC, EntityCategory.CONFIG], True, False),
        (EntityCategory.CONFIG, [EntityCategory.DIAGNOSTIC, EntityCategory.CONFIG], True, False),
        (None, [EntityCategory.DIAGNOSTIC, EntityCategory.CONFIG], False, False),
        # List with multiple string categories
        (EntityCategory.DIAGNOSTIC, ["diagnostic", "config"], True, False),
        (EntityCategory.CONFIG, ["diagnostic", "config"], True, False),
        (None, ["diagnostic", "config"], False, False),
        # List with mixed EntityCategory and string categories
        (EntityCategory.DIAGNOSTIC, [EntityCategory.DIAGNOSTIC, "config"], True, False),
        (EntityCategory.CONFIG, ["diagnostic", EntityCategory.CONFIG], True, False),
        (None, [EntityCategory.DIAGNOSTIC, "config"], False, False),
        # Invalid string category
        (EntityCategory.DIAGNOSTIC, "invalid_category", False, True),
    ],
)
async def test_category_filter(
    category: EntityCategory,
    filter_categories: EntityCategory | str | list[EntityCategory | str],
    expected_result: bool,
    expect_exception: bool,
) -> None:
    entry = RegistryEntryWithDefaults(entity_id="sensor.test", unique_id="abc", platform="test", entity_category=category)

    if expect_exception:
        with pytest.raises(SensorConfigurationError):
            CategoryFilter(filter_categories).is_valid(entry)
        return

    assert CategoryFilter(filter_categories).is_valid(entry) == expected_result


async def test_lambda_filter() -> None:
    entity_filter = LambdaFilter(lambda entity: entity.entity_id == "sensor.test")

    entry = RegistryEntryWithDefaults(entity_id="sensor.test", unique_id="abc", platform="test")
    assert entity_filter.is_valid(entry) is True

    entry = RegistryEntryWithDefaults(entity_id="sensor.test2", unique_id="abc", platform="test")
    assert entity_filter.is_valid(entry) is False


async def test_not_filter() -> None:
    assert NotFilter(NullFilter()).is_valid(_create_registry_entry()) is False


@pytest.mark.parametrize(
    "filter_type,filter_config,expected_type",
    [
        ("unknown", {}, NullFilter),
        (CONF_DOMAIN, {}, DomainFilter),
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


@pytest.mark.parametrize(
    "entity_device,entity_area,area,expected_result,expect_exception",
    [
        ("my-device", None, "kitchen", True, False),
        ("my-device", None, "Kitchen", True, False),
        (None, "bathroom", "bathroom", True, False),
        ("my_device", None, "nonexistent_area", False, True),
        # Test with list of areas
        ("my-device", None, ["kitchen", "bathroom"], True, False),
        (None, "bathroom", ["kitchen", "bathroom"], True, False),
        (None, "kitchen", ["bathroom"], False, False),
        ("my_device", None, ["nonexistent_area", "another_nonexistent"], False, True),
    ],
)
async def test_area_filter(
    hass: HomeAssistant,
    entity_device: str | None,
    entity_area: str | None,
    area: str | list[str],
    expected_result: bool,
    expect_exception: bool,
) -> None:
    area_reg = area_registry.async_get(hass)
    area_reg.async_get_or_create("Kitchen")
    area_reg.async_get_or_create("Bathroom")

    mock_device_registry(
        hass,
        {
            "my-device": DeviceEntry(
                id="my-device",
                name="My device",
                manufacturer="Mock",
                model="Device",
                area_id="kitchen",
            ),
        },
    )

    entry = RegistryEntryWithDefaults(
        entity_id="switch.test",
        unique_id="abc",
        platform="test",
        device_id=entity_device,
        area_id=entity_area,
    )
    if expect_exception:
        with pytest.raises(SensorConfigurationError):
            AreaFilter(hass, area).is_valid(entry)
        return

    assert AreaFilter(hass, area).is_valid(entry) == expected_result


@pytest.mark.parametrize(
    "group_id,entity_id,expected_result",
    [
        ("group.some_group", "light.test_light", True),
        ("group.some_group", "light.other_light", False),
        (["group.some_group", "group.other_group"], "light.test_light", True),
        (["group.some_group", "group.other_group"], "light.other_light", True),
        (["group.some_group", "group.other_group"], "light.unrelated_light", False),
    ],
)
async def test_group_filter(
    hass: HomeAssistant,
    group_id: str | list[str],
    entity_id: str,
    expected_result: bool,
) -> None:
    mock_registry(
        hass,
        {
            "group.some_group": RegistryEntryWithDefaults(
                entity_id="group.some_group",
                unique_id="def",
                platform="test",
            ),
            "group.other_group": RegistryEntryWithDefaults(
                entity_id="group.other_group",
                unique_id="ghi",
                platform="test",
            ),
        },
    )

    hass.states.async_set(
        "group.some_group",
        STATE_ON,
        {"entity_id": ["light.test_light"]},
    )
    hass.states.async_set(
        "group.other_group",
        "on",
        {"entity_id": ["light.other_light"]},
    )
    await hass.async_block_till_done()

    entry = RegistryEntryWithDefaults(entity_id=entity_id, unique_id="abc", platform="test")

    assert GroupFilter(hass, group_id).is_valid(entry) == expected_result


def _create_registry_entry(entity_id: str = "switch.test") -> RegistryEntry:
    return RegistryEntryWithDefaults(entity_id=entity_id, unique_id="abc", platform="test", device_id="my-device")
