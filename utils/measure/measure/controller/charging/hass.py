from __future__ import annotations

from measure.controller.charging.const import (
    ATTR_BATTERY_LEVEL,
    BatteryLevelSourceType,
)
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.errors import BatteryLevelRetrievalError
from measure.controller.hass_controller import HassControllerBase
from measure.home_assistant import HomeAssistantManager


class HassChargingController(HassControllerBase, ChargingController):
    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        *,
        entity_id: str | None = None,
        battery_level_source_type: BatteryLevelSourceType = BatteryLevelSourceType.ATTRIBUTE,
        battery_level_attribute: str | None = None,
        battery_level_entity_id: str | None = None,
    ) -> None:
        self.battery_level_attribute = (
            battery_level_attribute or ATTR_BATTERY_LEVEL
            if battery_level_source_type == BatteryLevelSourceType.ATTRIBUTE
            else None
        )
        self.battery_level_source_type = battery_level_source_type
        self.battery_level_entity_id = battery_level_entity_id
        super().__init__(home_assistant, entity_id=entity_id)

    def get_battery_level(self) -> int:
        """Get actual battery level of the device"""

        if self.battery_level_source_type == BatteryLevelSourceType.ATTRIBUTE:
            state = self.get_entity_state()
            if self.battery_level_attribute not in state.attributes:
                raise BatteryLevelRetrievalError(
                    f"Attribute {self.battery_level_attribute} not found in entity {self.entity_id}",
                )
            return int(state.attributes[self.battery_level_attribute])

        if not self.battery_level_entity_id:
            raise BatteryLevelRetrievalError("Battery level entity ID is not set")
        entity = self.client.get_entity(entity_id=self.battery_level_entity_id)
        if not entity:
            raise BatteryLevelRetrievalError(f"Battery level entity {self.battery_level_entity_id} not found")
        try:
            return int(float(entity.state.state))
        except ValueError, TypeError:
            raise BatteryLevelRetrievalError(
                f"Could not convert battery level entity state '{entity.state.state}' to integer",
            ) from None

    def is_charging(self) -> bool:
        """Check if the device is currently charging"""

        return self.get_entity_state().state == "docked"

    def is_valid_state(self) -> bool:
        """Check if the entity is in a valid state where it is available, either charging or performing tasks"""

        return self.get_entity_state().state in ["docked", "cleaning", "returning", "idle", "paused"]
