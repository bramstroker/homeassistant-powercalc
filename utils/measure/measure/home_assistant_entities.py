from __future__ import annotations

from enum import StrEnum
import math
from typing import Any

from pydantic import BaseModel, ConfigDict

from measure.const import (
    HASS_DEVICE_REGISTRY_ID,
    HASS_DEVICE_REGISTRY_MODEL,
    HASS_DEVICE_REGISTRY_MODEL_ID,
    HASS_ENTITY_DEVICE_CLASS,
    HASS_ENTITY_UNIT_OF_MEASUREMENT,
)
from measure.controller.light.capabilities import light_info_from_attributes, supported_light_modes
from measure.controller.light.const import LutMode
from measure.home_assistant import HomeAssistantManager


class EntityDomain(StrEnum):
    LIGHT = "light"
    MEDIA_PLAYER = "media_player"
    FAN = "fan"
    VACUUM = "vacuum"
    LAWN_MOWER = "lawn_mower"
    SENSOR = "sensor"


class DeviceClass(StrEnum):
    POWER = "power"
    VOLTAGE = "voltage"

    @property
    def unit_of_measurement(self) -> str:
        return "W" if self is DeviceClass.POWER else "V"


class EntityDescriptor(BaseModel):
    """Transport-neutral Home Assistant entity metadata used by selectors."""

    model_config = ConfigDict(frozen=True)

    entity_id: str
    name: str
    domain: EntityDomain
    device_class: DeviceClass | None = None
    device_id: str | None = None
    model_id: str | None = None
    state: str
    unit: str | None = None
    attribute_names: list[str]
    supported_modes: list[LutMode] | None = None
    effect_list: list[str] | None = None
    min_mired: int | None = None
    max_mired: int | None = None
    related_voltage_entity_id: str | None = None


class EntityCatalogSnapshot:
    """Immutable view used for one selector or preflight operation."""

    def __init__(self, entities: list[EntityDescriptor]) -> None:
        self._entities = tuple(entities)
        self._by_id = {entity.entity_id: entity for entity in entities}

    def select(
        self,
        *,
        domain: EntityDomain | None = None,
        device_class: DeviceClass | None = None,
    ) -> list[EntityDescriptor]:
        if (domain is None) == (device_class is None):
            raise ValueError("Specify exactly one entity filter")

        if domain is not None:
            selected = [
                entity for entity in self._entities if entity.domain == domain and self._is_domain_selectable(entity)
            ]
        else:
            assert device_class is not None
            selected = self._select_device_class(device_class)

        selected.sort(key=lambda entity: (entity.name.casefold(), entity.entity_id))
        if device_class == DeviceClass.POWER:
            selected = [
                entity.model_copy(
                    update={"related_voltage_entity_id": self._related_entity_id(entity, DeviceClass.VOLTAGE)},
                )
                for entity in selected
            ]
        return selected

    def attribute_names(self, entity_id: str) -> list[str]:
        entity = self._by_id.get(entity_id)
        return list(entity.attribute_names) if entity is not None else []

    def get(self, entity_id: str) -> EntityDescriptor | None:
        return self._by_id.get(entity_id)

    def related_entity_id(self, entity_id: str, device_class: DeviceClass) -> str | None:
        entity = self._by_id.get(entity_id)
        if entity is None:
            return None
        return self._related_entity_id(entity, device_class)

    def _related_entity_id(self, entity: EntityDescriptor, device_class: DeviceClass) -> str | None:
        if entity.device_id is None:
            return None
        return next(
            (
                candidate.entity_id
                for candidate in self._select_device_class(device_class)
                if candidate.device_id == entity.device_id
            ),
            None,
        )

    def _select_device_class(self, device_class: DeviceClass) -> list[EntityDescriptor]:
        return sorted(
            (entity for entity in self._entities if self._is_device_class_selectable(entity, device_class)),
            key=lambda entity: (entity.name.casefold(), entity.entity_id),
        )

    @staticmethod
    def _is_available(entity: EntityDescriptor) -> bool:
        return entity.state.casefold() not in {"unavailable", "unknown", "none"}

    @classmethod
    def _is_domain_selectable(cls, entity: EntityDescriptor) -> bool:
        return cls._is_available(entity) and (entity.domain != EntityDomain.LIGHT or bool(entity.supported_modes))

    @classmethod
    def _is_device_class_selectable(cls, entity: EntityDescriptor, device_class: DeviceClass) -> bool:
        return (
            cls._is_available(entity)
            and entity.domain == EntityDomain.SENSOR
            and entity.device_class == device_class
            and entity.unit == device_class.unit_of_measurement
            and _is_finite_number(entity.state)
        )


class HomeAssistantEntityCatalog:
    """Build reusable selector snapshots from Home Assistant data.

    The snapshot is loaded once per catalog instance; create a new catalog to see fresh data.
    Interactive question rendering re-evaluates choices on every keypress, so load_snapshot
    must not hit Home Assistant each call.
    """

    def __init__(self, home_assistant: HomeAssistantManager) -> None:
        self._home_assistant = home_assistant
        self._snapshot: EntityCatalogSnapshot | None = None

    def load_snapshot(self) -> EntityCatalogSnapshot:
        if self._snapshot is None:
            self._snapshot = self._build_snapshot()
        return self._snapshot

    def _build_snapshot(self) -> EntityCatalogSnapshot:
        data = self._home_assistant.get_entity_data()
        registry = {entry.entity_id: entry for entry in data.entity_registry}
        devices = {
            str(device_id): device
            for device in data.device_registry
            if (device_id := device.get(HASS_DEVICE_REGISTRY_ID)) is not None
        }
        descriptors: list[EntityDescriptor] = []
        for domain_value, group in data.entities.items():
            try:
                domain = EntityDomain(domain_value)
            except ValueError:
                continue
            descriptors.extend(
                _describe_entity(entity, domain, registry.get(entity.entity_id), devices)
                for entity in group.entities.values()
            )
        return EntityCatalogSnapshot(descriptors)


def _describe_entity(
    entity: Any,  # noqa: ANN401
    domain: EntityDomain,
    registry_entry: Any | None,  # noqa: ANN401
    device_registry: dict[str, dict[str, object]],
) -> EntityDescriptor:
    attributes = entity.state.attributes
    device_id = str(registry_entry.device_id) if registry_entry is not None and registry_entry.device_id else None
    device = device_registry.get(device_id, {}) if device_id is not None else {}
    model_id = device.get(HASS_DEVICE_REGISTRY_MODEL_ID) or device.get(HASS_DEVICE_REGISTRY_MODEL)
    device_class = _device_class(attributes.get(HASS_ENTITY_DEVICE_CLASS))
    supported_modes = supported_light_modes(attributes) if domain == EntityDomain.LIGHT else None
    light_info = light_info_from_attributes(attributes) if domain == EntityDomain.LIGHT else None
    unit = attributes.get(HASS_ENTITY_UNIT_OF_MEASUREMENT)
    return EntityDescriptor(
        entity_id=entity.entity_id,
        name=str(attributes.get("friendly_name", entity.entity_id)),
        domain=domain,
        device_class=device_class,
        device_id=device_id,
        model_id=str(model_id) if model_id else None,
        state=str(entity.state.state),
        unit=str(unit) if unit else None,
        attribute_names=sorted(attributes),
        supported_modes=supported_modes,
        effect_list=[str(effect) for effect in attributes.get("effect_list", [])] or None,
        min_mired=light_info.get_min_mired() if light_info is not None else None,
        max_mired=light_info.get_max_mired() if light_info is not None else None,
    )


def _device_class(value: object) -> DeviceClass | None:
    try:
        return DeviceClass(str(value))
    except ValueError:
        return None


def _is_finite_number(value: str) -> bool:
    try:
        return math.isfinite(float(value))
    except ValueError, TypeError:
        return False
