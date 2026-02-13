from collections.abc import Callable, Coroutine
import decimal
from decimal import Decimal
from functools import wraps
import logging
import os.path
import re
from typing import Any, TypeVar
import uuid

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import DUMMY_ENTITY_ID, CalculationStrategy
from custom_components.powercalc.power_profile.power_profile import PowerProfile

_LOGGER = logging.getLogger(__name__)

PLACEHOLDER_REGEX = re.compile(r"\[\[\s*([A-Za-z_]\w*(?::[A-Za-z_]\w*)*)\s*\]\]")


async def evaluate_power(power: Template | Decimal | float) -> Decimal | None:
    """When power is a template render it."""

    if isinstance(power, Decimal):
        return power

    try:
        if isinstance(power, Template):
            try:
                power = power.async_render()
            except TemplateError as ex:
                _LOGGER.error("Could not render power template %s: %s", power, ex)
                return None
            if power == "unknown":
                return None

        return Decimal(power)  # type: ignore[arg-type]
    except (decimal.DecimalException, ValueError):
        _LOGGER.error("Could not convert power value %s to decimal", power)
        return None


def get_library_path(sub_path: str = "") -> str:
    """Get the path to the library file."""
    base_path = os.path.join(os.path.dirname(__file__), "../../profile_library")
    return f"{base_path}/{sub_path}"


def get_library_json_path() -> str:
    """Get the path to the library.json file."""
    return get_library_path("library.json")


def get_or_create_unique_id(
    sensor_config: ConfigType,
    source_entity: SourceEntity,
    power_profile: PowerProfile | None,
) -> str:
    """Get or create the unique id."""
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    if unique_id:
        return str(unique_id)

    # For multi-switch and wled strategy we need to use the device id as unique id
    # As we don't want to start a discovery for each switch entity
    if (
        source_entity.device_entry
        and power_profile
        and power_profile.calculation_strategy in [CalculationStrategy.WLED, CalculationStrategy.MULTI_SWITCH]
    ):
        return f"pc_{source_entity.device_entry.id}"

    if source_entity and source_entity.entity_id != DUMMY_ENTITY_ID:
        source_unique_id = source_entity.unique_id or source_entity.entity_id
        # Prefix with pc_ to avoid conflicts with other integrations
        return f"pc_{source_unique_id}"

    return str(uuid.uuid4())


P = TypeVar("P")  # Used for positional and keyword argument types
R = TypeVar("R")  # Used for return type


def make_hashable(arg: Any) -> Any:  # noqa: ANN401
    """Convert unhashable arguments to hashable equivalents."""
    if isinstance(arg, set):
        return frozenset(arg)
    if isinstance(arg, list):
        return tuple(arg)
    if isinstance(arg, dict):
        return frozenset((key, make_hashable(value)) for key, value in arg.items())
    return arg


def async_cache[R](func: Callable[..., Coroutine[Any, Any, R]]) -> Callable[..., Coroutine[Any, Any, R]]:
    """
    A decorator to cache results of an async function based on its arguments.

    Args:
        func: The asynchronous function to decorate.

    Returns:
        A decorated asynchronous function with caching.
    """
    cache: dict[tuple[tuple[Any, ...], frozenset], R] = {}

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> R:  # noqa: ANN401
        # Make arguments hashable
        hashable_args = tuple(make_hashable(arg) for arg in args)
        hashable_kwargs = frozenset((key, make_hashable(value)) for key, value in kwargs.items())
        cache_key = (hashable_args, hashable_kwargs)

        if cache_key in cache:
            return cache[cache_key]
        result = await func(*args, **kwargs)
        cache[cache_key] = result
        return result

    return wrapper


def collect_placeholders(data: list | str | dict[str, Any]) -> set[str]:
    found: set[str] = set()
    if isinstance(data, dict):
        for v in data.values():
            found |= collect_placeholders(v)
    elif isinstance(data, list):
        for v in data:
            found |= collect_placeholders(v)
    elif isinstance(data, str):
        found |= set(PLACEHOLDER_REGEX.findall(data))
    return found


def replace_placeholders(data: list | str | dict[str, Any], replacements: dict[str, str]) -> list | str | dict[str, Any]:
    """Replace placeholders in a dictionary with values from a replacement dictionary."""
    if isinstance(data, dict):
        for key, value in data.items():
            data[key] = replace_placeholders(value, replacements)
    elif isinstance(data, list):
        for i in range(len(data)):
            data[i] = replace_placeholders(data[i], replacements)
    elif isinstance(data, str):
        # Use the same regex pattern as PLACEHOLDER_REGEX
        matches = PLACEHOLDER_REGEX.findall(data)
        for match in matches:
            if match in replacements:
                # Replace [[variable]] with its value
                data = data.replace(f"[[{match}]]", replacements[match])
    return data


def get_related_entity_by_device_class(
    hass: HomeAssistant,
    entity: RegistryEntry,
    device_class: SensorDeviceClass | BinarySensorDeviceClass,
) -> str | None:
    """Get related entity from same device by device class."""

    entity_reg = entity_registry.async_get(hass)
    device_id = entity.device_id
    if not device_id:
        _LOGGER.debug("Entity %s has no device_id, cannot find related entity", entity.entity_id)
        return None

    related_entities = [
        entity_entry.entity_id
        for entity_entry in entity_registry.async_entries_for_device(
            entity_reg,
            device_id,
        )
        if (entity_entry.device_class or entity_entry.original_device_class) == device_class
    ]
    if not related_entities:
        _LOGGER.debug("No related entities found for device %s with device class %s", device_id, device_class)
        return None

    return related_entities[0]
