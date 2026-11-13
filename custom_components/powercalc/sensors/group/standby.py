from decimal import Decimal
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, CONF_NAME, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType

from custom_components.powercalc.common import create_source_entity
from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_MEMBERS,
    ATTR_STATE,
    CONF_CREATE_ACTIVE_GROUP,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_ENERGY_SENSOR_FRIENDLY_NAMING,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_PRECISION,
    DATA_SELF_USAGE_POWER_SENSORS,
    DATA_STANDBY_POWER_SENSORS,
    DEFAULT_POWER_SENSOR_PRECISION,
    DOMAIN,
    DUMMY_ENTITY_ID,
    SIGNAL_POWER_SENSOR_STATE_CHANGE,
)
from custom_components.powercalc.sensors.energy import create_energy_sensor
from custom_components.powercalc.sensors.energy_related import create_energy_related_sensors
from custom_components.powercalc.sensors.power import PowerSensor

_LOGGER = logging.getLogger(__name__)


def create_general_standby_sensors(
    hass: HomeAssistant,
    config: ConfigType,
) -> list[Entity]:
    sensors: list[Entity] = []
    sensors.extend(_create_sum_sensors(hass, config, StandbyPowerSensor))
    if config.get(CONF_CREATE_ACTIVE_GROUP, False):
        sensors.extend(_create_sum_sensors(hass, config, SelfUsagePowerSensor))
    return sensors


def _create_sum_sensors(
    hass: HomeAssistant,
    config: ConfigType,
    sensor_class: type[SumPowerSensor],
) -> list[Entity]:
    """Create a total power sensor, optionally with its energy related sensors."""
    sensors: list[Entity] = []
    power_sensor = sensor_class(
        hass,
        rounding_digits=int(config.get(CONF_POWER_SENSOR_PRECISION, DEFAULT_POWER_SENSOR_PRECISION)),
        entity_category=config.get(CONF_POWER_SENSOR_CATEGORY),
    )
    power_sensor.entity_id = sensor_class.target_entity_id
    sensors.append(power_sensor)
    if config.get(CONF_CREATE_ENERGY_SENSORS):
        sensor_config = config.copy()
        sensor_config[CONF_NAME] = sensor_class.energy_name
        # A group total keeps its own name, the global energy naming pattern is meant for device sensors.
        sensor_config.pop(CONF_ENERGY_SENSOR_NAMING, None)
        sensor_config.pop(CONF_ENERGY_SENSOR_FRIENDLY_NAMING, None)
        source_entity = create_source_entity(DUMMY_ENTITY_ID, hass)
        energy_sensor = create_energy_sensor(
            hass,
            sensor_config,
            power_sensor,
            source_entity,
        )
        sensors.append(energy_sensor)
        if sensor_class.create_energy_related:
            sensors.extend(create_energy_related_sensors(hass, sensor_config, energy_sensor, source_entity))
    return sensors


class SumPowerSensor(PowerSensor, SensorEntity):
    """Total power of all power sensors tracked in a shared registry."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_has_entity_name = True

    data_key: str = ""
    target_entity_id: str = ""
    energy_name: str = ""
    create_energy_related: bool = True

    def __init__(
        self,
        hass: HomeAssistant,
        rounding_digits: int = 2,
        entity_category: str | None = None,
    ) -> None:
        self.sum_sensors: dict[str, Decimal] = hass.data[DOMAIN][self.data_key]
        self._rounding_digits = rounding_digits
        if entity_category:
            self._attr_entity_category = EntityCategory(entity_category)

    async def async_added_to_hass(self) -> None:
        """Register state listeners."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_POWER_SENSOR_STATE_CHANGE,
                self._recalculate,
            ),
        )
        await self._recalculate()

    async def _recalculate(self) -> None:
        """Calculate the sum of all tracked power sensors and update the state."""
        if self.sum_sensors:
            self._attr_native_value = Decimal(
                round(
                    sum(self.sum_sensors.values(), Decimal(0)),
                    self._rounding_digits,
                ),
            )
        else:
            self._attr_native_value = None
        self.async_schedule_update_ha_state(True)

    def get_group_entities(self) -> dict[str, set[str]]:
        return {ATTR_ENTITIES: set(self.sum_sensors)}

    def debug_group(self) -> dict[str, Any]:
        """Return the current contribution of each tracked power sensor."""
        members = {
            entity_id: {
                ATTR_STATE: str(round(power, self._rounding_digits)),
                ATTR_UNIT_OF_MEASUREMENT: self.native_unit_of_measurement,
            }
            for entity_id, power in sorted(self.sum_sensors.items())
        }
        return {
            ATTR_STATE: str(self.state),
            ATTR_UNIT_OF_MEASUREMENT: self.native_unit_of_measurement,
            ATTR_MEMBERS: members,
        }


class StandbyPowerSensor(SumPowerSensor):
    """Sum of the standby power of all devices that are currently turned off."""

    _attr_unique_id = "powercalc_standby_group"
    _attr_name = "All standby power"

    data_key = DATA_STANDBY_POWER_SENSORS
    target_entity_id = "sensor.all_standby_power"
    energy_name = "All standby"


class SelfUsagePowerSensor(SumPowerSensor):
    """Sum of the self-usage power of all devices that are currently turned on."""

    _attr_unique_id = "powercalc_self_usage_group"
    _attr_name = "All self usage power"

    data_key = DATA_SELF_USAGE_POWER_SENSORS
    target_entity_id = "sensor.all_self_usage_power"
    energy_name = "All self usage"
    create_energy_related = False
