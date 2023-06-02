from __future__ import annotations

from typing import Protocol

from homeassistant.backports.enum import StrEnum
from homeassistant.const import CONF_DOMAIN
from homeassistant.helpers.entity_registry import RegistryEntry


class FilterOperator(StrEnum):
    AND = "and"
    OR = "or"


def create_filter(filter_config: dict) -> IncludeEntityFilter:
    """Create filter class."""
    filters: list[IncludeEntityFilter] = []
    if CONF_DOMAIN in filter_config:
        domain_config = filter_config.get(CONF_DOMAIN)
        if type(domain_config) == list:
            filters.append(
                CompositeFilter(
                    [DomainFilter(domain) for domain in domain_config],
                    FilterOperator.OR,
                ),
            )
        elif type(domain_config) == str:
            filters.append(DomainFilter(domain_config))

    return CompositeFilter(filters, FilterOperator.AND)


class IncludeEntityFilter(Protocol):
    def is_valid(self, entity: RegistryEntry) -> bool:
        """Return True when the entity should be included, False when it should be discarded."""
        ...


class DomainFilter(IncludeEntityFilter):
    def __init__(self, domain: str) -> None:
        self.domain: str = domain

    def is_valid(self, entity: RegistryEntry) -> bool:
        return entity.domain == self.domain


class NullFilter(IncludeEntityFilter):
    def is_valid(self, entity: RegistryEntry) -> bool:
        return True


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
