"""Status sensor for the separately installed Powercalc Measure app."""

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from custom_components.powercalc.measure import MEASURE_SESSION_STATES, MeasureAppCoordinator


class MeasureSessionStatusSensor(SensorEntity):
    """Represent the current or most recently retained Measure session."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "measure_session_status"
    _attr_unique_id = "measure_session_status"

    def __init__(self, coordinator: MeasureAppCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_options = list(MEASURE_SESSION_STATES)

    @property
    def native_value(self) -> str | None:
        """Return the latest session state."""
        return self._coordinator.data.state if self._coordinator.data is not None else None

    @property
    def available(self) -> bool:
        """Return whether the Measure app heartbeat is current."""
        return self._coordinator.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return stable metadata useful in completion and failure automations."""
        status = self._coordinator.data
        if status is None:
            return {}
        attributes: dict[str, Any] = {"app_version": status.app_version}
        if status.session_id is not None:
            attributes["session_id"] = status.session_id
        if status.error is not None:
            attributes["error"] = status.error
        return attributes

    async def async_added_to_hass(self) -> None:
        """Subscribe after the entity has been attached to Home Assistant."""
        await super().async_added_to_hass()
        self.async_on_remove(self._coordinator.async_add_listener(self.async_write_ha_state))
