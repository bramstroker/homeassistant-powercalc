from __future__ import annotations

from enum import StrEnum
import re
from typing import NamedTuple, Protocol

from homeassistant.core import HomeAssistant, State

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.errors import PowercalcSetupError


class SubProfileMatcherType(StrEnum):
    ATTRIBUTE = "attribute"
    ENTITY_ID = "entity_id"
    ENTITY_REGISTRY = "entity_registry"
    ENTITY_STATE = "entity_state"
    INTEGRATION = "integration"
    MODEL_ID = "model_id"


class SubProfileSelector:
    def __init__(
        self,
        hass: HomeAssistant,
        config: SubProfileSelectConfig,
        source_entity: SourceEntity,
    ) -> None:
        self._hass = hass
        self._config = config
        self._source_entity = source_entity
        self._matchers: list[SubProfileMatcher] = self._build_matchers()

    def _build_matchers(self) -> list[SubProfileMatcher]:
        """Create matchers from json config."""
        return [self._create_matcher(matcher_config) for matcher_config in self._config.matchers or []]

    def select_sub_profile(self, entity_state: State) -> str:
        """Dynamically tries to select a sub profile depending on the entity state.
        This method always need to return a sub profile, when nothing is matched it will return a default.
        """
        for matcher in self._matchers:
            sub_profile = matcher.match(entity_state, self._source_entity)
            if sub_profile:
                return sub_profile

        return self._config.default

    def get_tracking_entities(self) -> list[str]:
        """Get additional list of entities to track for state changes."""
        return [entity_id for matcher in self._matchers for entity_id in matcher.get_tracking_entities()]

    def _create_matcher(self, matcher_config: dict) -> SubProfileMatcher:
        """Create a matcher from json config. Can be extended for more matchers in the future."""
        matcher_type: SubProfileMatcherType = matcher_config["type"]

        matcher_classes: dict[SubProfileMatcherType, type[SubProfileMatcher]] = {
            SubProfileMatcherType.ATTRIBUTE: AttributeMatcher,
            SubProfileMatcherType.ENTITY_STATE: EntityStateMatcher,
            SubProfileMatcherType.ENTITY_ID: EntityIdMatcher,
            SubProfileMatcherType.ENTITY_REGISTRY: EntityRegistryMatcher,
            SubProfileMatcherType.INTEGRATION: IntegrationMatcher,
            SubProfileMatcherType.MODEL_ID: ModelIdMatcher,
        }
        if matcher_type not in matcher_classes:
            raise PowercalcSetupError(f"Unknown sub profile matcher type: {matcher_type}")

        return matcher_classes[matcher_type].from_config(
            matcher_config,
            hass=self._hass,
            source_entity=self._source_entity,
        )


class SubProfileSelectConfig(NamedTuple):
    default: str
    matchers: list[dict] | None = None


class SubProfileMatcher(Protocol):
    @classmethod
    def from_config(
        cls,
        config: dict,
        *,
        hass: HomeAssistant | None = None,
        source_entity: SourceEntity | None = None,
    ) -> SubProfileMatcher:
        """Create a matcher from a config dict."""

    def match(self, entity_state: State, source_entity: SourceEntity) -> str | None:
        """Returns a sub profile."""

    def get_tracking_entities(self) -> list[str]:
        """Get extra entities to track for state changes."""


class EntityStateMatcher(SubProfileMatcher):
    def __init__(
        self,
        hass: HomeAssistant,
        source_entity: SourceEntity | None,
        entity_id: str,
        mapping: dict[str, str],
    ) -> None:
        self._hass = hass
        if source_entity:
            entity_id = entity_id.replace(
                "{{source_object_id}}",
                source_entity.object_id,
            )
        self._entity_id = entity_id
        self._mapping = mapping

    def match(self, entity_state: State, source_entity: SourceEntity) -> str | None:
        state = self._hass.states.get(self._entity_id)
        if state is None:
            return None

        return self._mapping.get(state.state)

    @classmethod
    def from_config(
        cls,
        config: dict,
        *,
        hass: HomeAssistant | None = None,
        source_entity: SourceEntity | None = None,
    ) -> EntityStateMatcher:
        assert hass is not None
        return cls(hass, source_entity, config["entity_id"], config["map"])

    def get_tracking_entities(self) -> list[str]:
        return [self._entity_id]


class AttributeMatcher(SubProfileMatcher):
    def __init__(self, attribute: str, mapping: dict[str, str]) -> None:
        self._attribute = attribute
        self._mapping = mapping

    def match(self, entity_state: State, source_entity: SourceEntity) -> str | None:
        val = entity_state.attributes.get(self._attribute)
        if val is None:
            return None

        return self._mapping.get(val)

    @classmethod
    def from_config(
        cls,
        config: dict,
        *,
        hass: HomeAssistant | None = None,
        source_entity: SourceEntity | None = None,
    ) -> AttributeMatcher:
        return cls(config["attribute"], config["map"])

    def get_tracking_entities(self) -> list[str]:
        return []


class EntityIdMatcher(SubProfileMatcher):
    def __init__(self, pattern: str, profile: str) -> None:
        self._pattern = pattern
        self._profile = profile

    def match(self, entity_state: State, source_entity: SourceEntity) -> str | None:
        if re.search(self._pattern, entity_state.entity_id):
            return self._profile

        return None

    @classmethod
    def from_config(
        cls,
        config: dict,
        *,
        hass: HomeAssistant | None = None,
        source_entity: SourceEntity | None = None,
    ) -> EntityIdMatcher:
        return cls(config["pattern"], config["profile"])

    def get_tracking_entities(self) -> list[str]:
        return []


class IntegrationMatcher(SubProfileMatcher):
    def __init__(self, integration: str, profile: str) -> None:
        self._integration = integration
        self._profile = profile

    def match(self, entity_state: State, source_entity: SourceEntity) -> str | None:
        registry_entry = source_entity.entity_entry
        if not registry_entry:
            return None

        if registry_entry.platform == self._integration:
            return self._profile

        return None

    @classmethod
    def from_config(
        cls,
        config: dict,
        *,
        hass: HomeAssistant | None = None,
        source_entity: SourceEntity | None = None,
    ) -> IntegrationMatcher:
        return cls(config["integration"], config["profile"])

    def get_tracking_entities(self) -> list[str]:
        return []


class EntityRegistryMatcher(SubProfileMatcher):
    def __init__(self, property_name: str, value: object, profile: str) -> None:
        self._property_name = property_name
        self._value = value
        self._profile = profile

    def match(self, entity_state: State, source_entity: SourceEntity) -> str | None:
        registry_entry = source_entity.entity_entry
        if not registry_entry or not hasattr(registry_entry, self._property_name):
            return None

        registry_value = getattr(registry_entry, self._property_name)
        if registry_value is None:
            return None

        if self._matches_registry_value(registry_value):
            return self._profile

        return None

    @classmethod
    def from_config(
        cls,
        config: dict,
        *,
        hass: HomeAssistant | None = None,
        source_entity: SourceEntity | None = None,
    ) -> EntityRegistryMatcher:
        return cls(config["property"], config["value"], config["profile"])

    def get_tracking_entities(self) -> list[str]:
        return []

    def _matches_registry_value(self, registry_value: object) -> bool:
        if registry_value == self._value:
            return True

        if isinstance(registry_value, list | set | tuple | frozenset):
            return self._value in registry_value

        return str(registry_value) == str(self._value)


class ModelIdMatcher(SubProfileMatcher):
    def __init__(self, model_id: str, profile: str) -> None:
        self._model_id = model_id
        self._profile = profile

    def match(self, entity_state: State, source_entity: SourceEntity) -> str | None:
        device_entry = source_entity.device_entry
        if not device_entry:
            return None

        if device_entry.model_id == self._model_id:
            return self._profile

        return None

    @classmethod
    def from_config(
        cls,
        config: dict,
        *,
        hass: HomeAssistant | None = None,
        source_entity: SourceEntity | None = None,
    ) -> ModelIdMatcher:
        return cls(config["model_id"], config["profile"])

    def get_tracking_entities(self) -> list[str]:
        return []
