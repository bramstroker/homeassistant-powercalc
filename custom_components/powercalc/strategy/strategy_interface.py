from decimal import Decimal
from typing import Optional

from homeassistant.core import State
from homeassistant.helpers.event import TrackTemplate

from custom_components.powercalc.common import SourceEntity


class PowerCalculationStrategyInterface:
    async def calculate(self, entity_state: State) -> Optional[Decimal]:
        """Calculate power consumption based on entity state"""
        pass

    async def validate_config(self, source_entity: SourceEntity):
        """Validate correct setup of the strategy"""
        pass

    def get_entities_to_track(self) -> list[str, TrackTemplate]:
        return []

    def can_calculate_standby(self) -> bool:
        return False
