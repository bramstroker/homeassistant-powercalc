from __future__ import annotations

from measure.controller.charging.const import ATTR_BATTERY_LEVEL
from measure.controller.charging.controller import ChargingController
from measure.controller.charging.errors import BatteryLevelRetrievalError
from measure.controller.hass_controller import HassControllerBase
from measure.home_assistant import HomeAssistantManager
from measure.home_assistant_entities import DeviceClass, HomeAssistantEntityCatalog


class HassChargingController(HassControllerBase, ChargingController):
    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        *,
        entity_id: str | None = None,
    ) -> None:
        self._battery_source_resolved = False
        self._battery_sensor_entity_id: str | None = None
        super().__init__(home_assistant, entity_id=entity_id)

    @property
    def battery_level_attribute(self) -> str | None:
        """Return the profile attribute only when attribute fallback was resolved."""
        if not self._battery_source_resolved or self._battery_sensor_entity_id is not None:
            return None
        return ATTR_BATTERY_LEVEL

    def get_battery_level(self) -> int:
        """Get actual battery level of the device"""

        # Modern Home Assistant integrations (e.g. dreame-vacuum) expose the battery level as a
        # separate battery sensor rather than an attribute of the main entity. Prefer such a
        # sensor on the same device, falling back to the battery_level attribute when none exists.
        sensor_entity_id = self._resolve_battery_sensor()
        if sensor_entity_id is not None:
            return self._read_battery_level_entity(sensor_entity_id)

        state = self.get_entity_state()
        if ATTR_BATTERY_LEVEL not in state.attributes:
            raise BatteryLevelRetrievalError(
                f"No battery level sensor found on the same device and attribute "
                f"{ATTR_BATTERY_LEVEL} not found in entity {self.entity_id}",
            )
        return int(state.attributes[ATTR_BATTERY_LEVEL])

    def _discover_battery_sensor(self) -> str | None:
        """Find a battery sensor belonging to the same device as the charging entity."""

        if not self.entity_id:
            return None
        snapshot = HomeAssistantEntityCatalog(self.client).load_snapshot()
        return snapshot.related_entity_id(self.entity_id, DeviceClass.BATTERY)

    def _resolve_battery_sensor(self) -> str | None:
        """Resolve and cache the battery source for the lifetime of this controller."""
        if not self._battery_source_resolved:
            self._battery_sensor_entity_id = self._discover_battery_sensor()
            self._battery_source_resolved = True
        return self._battery_sensor_entity_id

    def _read_battery_level_entity(self, entity_id: str) -> int:
        entity = self.client.get_entity(entity_id=entity_id)
        if not entity:
            raise BatteryLevelRetrievalError(f"Battery level entity {entity_id} not found")
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
