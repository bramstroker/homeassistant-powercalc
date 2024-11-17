from __future__ import annotations

import re
from collections.abc import Callable
from enum import StrEnum
from typing import Protocol, cast

from homeassistant.components.group import DOMAIN as GROUP_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_DOMAIN
from homeassistant.const import __version__ as HA_VERSION  # noqa
from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.helpers import area_registry, device_registry, entity_registry
from homeassistant.helpers.area_registry import AreaEntry
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.const import (
    CONF_ALL,
    CONF_AND,
    CONF_AREA,
    CONF_FILTER,
    CONF_GROUP,
    CONF_OR,
    CONF_TEMPLATE,
    CONF_WILDCARD,
)
from custom_components.powercalc.errors import SensorConfigurationError


class FilterOperator(StrEnum):
    AND = "and"
    OR = "or"


def create_composite_filter(
    filter_configs: ConfigType | list[ConfigType],
    hass: HomeAssistant,
    filter_operator: FilterOperator,
) -> IncludeEntityFilter:
    """Create filter class."""
    filters: list[IncludeEntityFilter] = []

    if CONF_FILTER in filter_configs and isinstance(filter_configs, dict):
        filter_configs.update(filter_configs[CONF_FILTER])
        filter_configs.pop(CONF_FILTER)

    if not isinstance(filter_configs, list):
        filter_configs = [{key: value} for key, value in filter_configs.items()]

    for filter_config in filter_configs:
        for key, val in filter_config.items():
            filter_instance = create_filter(key, val, hass)
            filters.append(filter_instance)

    return CompositeFilter(filters, filter_operator)


def create_filter(
    filter_type: str,
    filter_config: ConfigType | str | list | Template,
    hass: HomeAssistant,
) -> IncludeEntityFilter:
    filter_mapping: dict[str, Callable[[], IncludeEntityFilter]] = {
        CONF_DOMAIN: lambda: DomainFilter(filter_config),  # type: ignore
        CONF_AREA: lambda: AreaFilter(hass, filter_config),  # type: ignore
        CONF_WILDCARD: lambda: WildcardFilter(filter_config),  # type: ignore
        CONF_GROUP: lambda: GroupFilter(hass, filter_config),  # type: ignore
        CONF_TEMPLATE: lambda: TemplateFilter(hass, filter_config),  # type: ignore
        CONF_ALL: lambda: NullFilter(),
        CONF_OR: lambda: create_composite_filter(filter_config, hass, FilterOperator.OR),  # type: ignore
        CONF_AND: lambda: create_composite_filter(filter_config, hass, FilterOperator.AND),  # type: ignore
    }

    return filter_mapping.get(filter_type, lambda: NullFilter())()


class IncludeEntityFilter(Protocol):
    def is_valid(self, entity: RegistryEntry) -> bool:
        """Return True when the entity should be included, False when it should be discarded."""


class DomainFilter(IncludeEntityFilter):
    def __init__(self, domain: str | list) -> None:
        self.domain = domain

    def is_valid(self, entity: RegistryEntry) -> bool:
        if isinstance(self.domain, list):
            return entity.domain in self.domain
        return entity.domain == self.domain


class GroupFilter(IncludeEntityFilter):
    def __init__(self, hass: HomeAssistant, group_id: str) -> None:
        domain = split_entity_id(group_id)[0]
        self.filter = LightGroupFilter(hass, group_id) if domain == LIGHT_DOMAIN else StandardGroupFilter(hass, group_id)

    def is_valid(self, entity: RegistryEntry) -> bool:
        return self.filter.is_valid(entity)


class StandardGroupFilter(IncludeEntityFilter):
    def __init__(self, hass: HomeAssistant, group_id: str) -> None:
        entity_reg = entity_registry.async_get(hass)
        entity_reg.async_get(group_id)
        group_state = hass.states.get(group_id)
        if group_state is None:
            raise SensorConfigurationError(f"Group state {group_id} not found")
        self.entity_ids = group_state.attributes.get(ATTR_ENTITY_ID) or []

    def is_valid(self, entity: RegistryEntry) -> bool:
        return entity.entity_id in self.entity_ids


class LightGroupFilter(IncludeEntityFilter):
    def __init__(self, hass: HomeAssistant, group_id: str) -> None:
        light_component = cast(EntityComponent, hass.data.get(LIGHT_DOMAIN))
        light_group = next(
            filter(
                lambda entity: entity.entity_id == group_id,
                light_component.entities,
            ),
            None,
        )
        if light_group is None or light_group.platform.platform_name != GROUP_DOMAIN:
            raise SensorConfigurationError(f"Light group {group_id} not found")

        self.entity_ids = self.find_all_entity_ids_recursively(hass, group_id, [])

    def is_valid(self, entity: RegistryEntry) -> bool:
        return entity.entity_id in self.entity_ids

    def find_all_entity_ids_recursively(
        self,
        hass: HomeAssistant,
        group_entity_id: str,
        all_entity_ids: list[str],
    ) -> list[str]:
        entity_reg = entity_registry.async_get(hass)
        light_component = cast(EntityComponent, hass.data.get(LIGHT_DOMAIN))
        light_group = next(
            filter(
                lambda entity: entity.entity_id == group_entity_id,
                light_component.entities,
            ),
            None,
        )

        entity_ids: list[str] = light_group.extra_state_attributes.get(ATTR_ENTITY_ID)  # type: ignore
        for entity_id in entity_ids:
            registry_entry = entity_reg.async_get(entity_id)
            if registry_entry is None:
                continue

            if registry_entry.platform == GROUP_DOMAIN:
                self.find_all_entity_ids_recursively(
                    hass,
                    registry_entry.entity_id,
                    all_entity_ids,
                )

            all_entity_ids.append(entity_id)

        return all_entity_ids


class NullFilter(IncludeEntityFilter):
    def is_valid(self, entity: RegistryEntry) -> bool:
        return True


class WildcardFilter(IncludeEntityFilter):
    def __init__(self, pattern: str) -> None:
        self.regex = self.create_regex(pattern)

    def is_valid(self, entity: RegistryEntry) -> bool:
        return re.search(self.regex, entity.entity_id) is not None

    @staticmethod
    def create_regex(pattern: str) -> str:
        pattern = pattern.replace("?", ".")
        pattern = pattern.replace("*", ".*")
        return "^" + pattern + "$"


class TemplateFilter(IncludeEntityFilter):
    def __init__(self, hass: HomeAssistant, template: Template) -> None:
        template.hass = hass
        self.entity_ids = template.async_render()

    def is_valid(self, entity: RegistryEntry) -> bool:
        return entity.entity_id in self.entity_ids


class AreaFilter(IncludeEntityFilter):
    def __init__(self, hass: HomeAssistant, area_id_or_name: str) -> None:
        area_reg = area_registry.async_get(hass)
        area = area_reg.async_get_area(area_id_or_name)
        if area is None:
            area = area_reg.async_get_area_by_name(str(area_id_or_name))

        if area is None or area.id is None:
            raise SensorConfigurationError(
                f"No area with id or name '{area_id_or_name}' found in your HA instance",
            )

        self.area: AreaEntry = area

        device_reg = device_registry.async_get(hass)
        self.area_devices = [device.id for device in device_registry.async_entries_for_area(device_reg, area.id)]

    def is_valid(self, entity: RegistryEntry) -> bool:
        return entity.area_id == self.area.id or entity.device_id in self.area_devices


class CompositeFilter(IncludeEntityFilter):
    def __init__(
        self,
        filters: list[IncludeEntityFilter],
        operator: FilterOperator,
    ) -> None:
        self.filters = filters
        self.operator = operator

    def is_valid(self, entity: RegistryEntry) -> bool:
        evaluations = [entity_filter.is_valid(entity) for entity_filter in self.filters]
        if self.operator == FilterOperator.OR:
            return any(evaluations)

        return all(evaluations)
