import decimal
import logging
import os.path
import uuid
from decimal import Decimal

from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import DUMMY_ENTITY_ID, CalculationStrategy
from custom_components.powercalc.power_profile.power_profile import PowerProfile

_LOGGER = logging.getLogger(__name__)


async def evaluate_power(power: Template | Decimal | float) -> Decimal | None:
    """When power is a template render it."""

    if isinstance(power, Decimal):
        return power

    try:
        if isinstance(power, Template):
            power = power.async_render()
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


def get_or_create_unique_id(sensor_config: ConfigType, source_entity: SourceEntity, power_profile: PowerProfile | None) -> str:
    """Get or create the unique id."""
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    if unique_id:
        return str(unique_id)

    # For multi-switch strategy we need to use the device id as unique id
    # As we don't want to start a discovery for each switch entity
    if power_profile and power_profile.calculation_strategy == CalculationStrategy.MULTI_SWITCH and source_entity.device_entry:
        return f"pc_{source_entity.device_entry.id}"

    if source_entity and source_entity.entity_id != DUMMY_ENTITY_ID:
        source_unique_id = source_entity.unique_id or source_entity.entity_id
        # Prefix with pc_ to avoid conflicts with other integrations
        return f"pc_{source_unique_id}"

    return str(uuid.uuid4())
