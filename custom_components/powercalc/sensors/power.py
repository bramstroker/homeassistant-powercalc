from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import homeassistant.helpers.entity_registry as er
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.sensor import STATE_CLASS_MEASUREMENT, SensorEntity
from homeassistant.const import (
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_UNIQUE_ID,
    DEVICE_CLASS_POWER,
    EVENT_HOMEASSISTANT_START,
    POWER_WATT,
    STATE_NOT_HOME,
    STATE_OFF,
    STATE_STANDBY,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.typing import DiscoveryInfoType, HomeAssistantType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    ATTR_CALCULATION_MODE,
    ATTR_INTEGRATION,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_DISABLE_STANDBY_POWER,
    CONF_FIXED,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_LINEAR,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_STANDBY_POWER,
    CONF_WLED,
    DATA_CALCULATOR_FACTORY,
    DISCOVERY_LIGHT_MODEL,
    DOMAIN,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_WLED,
)
from custom_components.powercalc.errors import (
    ModelNotSupported,
    StrategyConfigurationError,
    UnsupportedMode,
)
from custom_components.powercalc.migrate import async_migrate_entity_id
from custom_components.powercalc.model_discovery import get_light_model
from custom_components.powercalc.strategy.strategy_interface import (
    PowerCalculationStrategyInterface,
)

ENTITY_ID_FORMAT = SENSOR_DOMAIN + ".{}"
OFF_STATES = [STATE_OFF, STATE_NOT_HOME, STATE_STANDBY, STATE_UNAVAILABLE]

_LOGGER = logging.getLogger(__name__)


async def create_power_sensor(
    hass: HomeAssistantType,
    sensor_config: dict,
    source_entity: SourceEntity,
    discovery_info: DiscoveryInfoType | None = None,
) -> PowerSensor:
    """Create the power sensor based on powercalc sensor configuration"""

    if CONF_POWER_SENSOR_ID in sensor_config:
        # Use an existing power sensor, only create energy sensors / utility meters
        return await create_real_power_sensor(hass, sensor_config)

    return await create_virtual_power_sensor(
        hass, sensor_config, source_entity, discovery_info
    )


async def create_virtual_power_sensor(
    hass: HomeAssistantType,
    sensor_config: dict,
    source_entity: SourceEntity,
    discovery_info: DiscoveryInfoType | None = None,
) -> VirtualPowerSensor:
    """Create the power sensor entity"""
    calculation_strategy_factory = hass.data[DOMAIN][DATA_CALCULATOR_FACTORY]

    name_pattern = sensor_config.get(CONF_POWER_SENSOR_NAMING)
    name = sensor_config.get(CONF_NAME) or source_entity.name
    name = name_pattern.format(name)
    object_id = sensor_config.get(CONF_NAME) or source_entity.object_id
    entity_id = async_generate_entity_id(
        ENTITY_ID_FORMAT, name_pattern.format(object_id), hass=hass
    )

    unique_id = sensor_config.get(CONF_UNIQUE_ID) or source_entity.unique_id
    if unique_id:
        async_migrate_entity_id(hass, SENSOR_DOMAIN, unique_id, entity_id)

    light_model = None
    try:
        mode = select_calculation_mode(sensor_config)

        if (
            sensor_config.get(CONF_LINEAR) is None
            and sensor_config.get(CONF_FIXED) is None
            and sensor_config.get(CONF_WLED) is None
        ):
            # When the user did not manually configured a model and a model was auto discovered we can load it.
            if (
                discovery_info
                and sensor_config.get(CONF_MODEL) is None
                and discovery_info.get(DISCOVERY_LIGHT_MODEL)
            ):
                light_model = discovery_info.get(DISCOVERY_LIGHT_MODEL)
            else:
                light_model = await get_light_model(
                    hass, sensor_config, source_entity.entity_entry
                )
            if mode is None and light_model:
                mode = light_model.supported_modes[0]

        if mode is None:
            raise UnsupportedMode(
                "Cannot select a mode (LINEAR, FIXED or LUT, WLED), supply it in the config"
            )

        calculation_strategy = calculation_strategy_factory.create(
            sensor_config, mode, light_model, source_entity
        )
        await calculation_strategy.validate_config(source_entity)
    except (ModelNotSupported, UnsupportedMode) as err:
        _LOGGER.error("Skipping sensor setup %s: %s", source_entity.entity_id, err)
        raise err
    except StrategyConfigurationError as err:
        _LOGGER.error(
            "%s: Error setting up calculation strategy: %s",
            source_entity.entity_id,
            err,
        )
        raise err

    standby_power = None
    if not sensor_config.get(CONF_DISABLE_STANDBY_POWER):
        standby_power = sensor_config.get(CONF_STANDBY_POWER)
        if standby_power is None and light_model is not None:
            standby_power = light_model.standby_power

    _LOGGER.debug(
        "Creating power sensor (entity_id=%s sensor_name=%s strategy=%s manufacturer=%s model=%s standby_power=%s unique_id=%s)",
        source_entity.entity_id,
        name,
        calculation_strategy.__class__.__name__,
        light_model.manufacturer if light_model else "",
        light_model.model if light_model else "",
        standby_power,
        unique_id,
    )

    return VirtualPowerSensor(
        power_calculator=calculation_strategy,
        calculation_mode=mode,
        entity_id=entity_id,
        name=name,
        source_entity=source_entity.entity_id,
        source_domain=source_entity.domain,
        unique_id=unique_id,
        standby_power=standby_power,
        scan_interval=sensor_config.get(CONF_SCAN_INTERVAL),
        multiply_factor=sensor_config.get(CONF_MULTIPLY_FACTOR),
        multiply_factor_standby=sensor_config.get(CONF_MULTIPLY_FACTOR_STANDBY),
        ignore_unavailable_state=sensor_config.get(CONF_IGNORE_UNAVAILABLE_STATE),
        rounding_digits=sensor_config.get(CONF_POWER_SENSOR_PRECISION),
    )


async def create_real_power_sensor(
    hass: HomeAssistantType, sensor_config: dict
) -> RealPowerSensor:
    """Create reference to an existing power sensor"""

    power_sensor_id = sensor_config.get(CONF_POWER_SENSOR_ID)
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    device_id = None
    ent_reg = er.async_get(hass)
    entity_entry = ent_reg.async_get(power_sensor_id)
    if entity_entry:
        if not unique_id:
            unique_id = entity_entry.unique_id
        device_id = entity_entry.device_id

    return RealPowerSensor(
        entity_id=power_sensor_id, device_id=device_id, unique_id=unique_id
    )


def select_calculation_mode(config: dict) -> Optional[str]:
    """Select the calculation mode"""
    config_mode = config.get(CONF_MODE)
    if config_mode:
        return config_mode

    if config.get(CONF_LINEAR):
        return MODE_LINEAR

    if config.get(CONF_FIXED):
        return MODE_FIXED

    if config.get(CONF_WLED):
        return MODE_WLED

    return None


class PowerSensor:
    """Class which all power sensors should extend from"""

    pass


class VirtualPowerSensor(SensorEntity, PowerSensor):
    """Virtual power sensor"""

    _attr_device_class = DEVICE_CLASS_POWER
    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_unit_of_measurement = POWER_WATT

    def __init__(
        self,
        power_calculator: PowerCalculationStrategyInterface,
        calculation_mode: str,
        entity_id: str,
        name: str,
        source_entity: str,
        source_domain: str,
        unique_id: str,
        standby_power: float | None,
        scan_interval,
        multiply_factor: float | None,
        multiply_factor_standby: bool,
        ignore_unavailable_state: bool,
        rounding_digits: int,
    ):
        """Initialize the sensor."""
        self._power_calculator = power_calculator
        self._calculation_mode = calculation_mode
        self._source_entity = source_entity
        self._source_domain = source_domain
        self._name = name
        self._power = None
        self._standby_power = standby_power
        self._attr_force_update = True
        self._attr_unique_id = unique_id
        self._scan_interval = scan_interval
        self._multiply_factor = multiply_factor
        self._multiply_factor_standby = multiply_factor_standby
        self._ignore_unavailable_state = ignore_unavailable_state
        self._rounding_digits = rounding_digits
        self.entity_id = entity_id

    async def async_added_to_hass(self):
        """Register callbacks."""

        async def appliance_state_listener(event):
            """Handle for state changes for dependent sensors."""
            new_state = event.data.get("new_state")

            await self._update_power_sensor(self._source_entity, new_state)

        async def home_assistant_startup(event):
            """Add listeners and get initial state."""
            tracked_entities = self._power_calculator.get_entities_to_track()
            if not tracked_entities:
                tracked_entities = {self._source_entity}

            async_track_state_change_event(
                self.hass, tracked_entities, appliance_state_listener
            )

            for entity_id in tracked_entities:
                new_state = self.hass.states.get(entity_id)

                await self._update_power_sensor(entity_id, new_state)

        @callback
        def async_update(event_time=None):
            """Update the entity."""
            self.async_schedule_update_ha_state(True)

        async_track_time_interval(self.hass, async_update, self._scan_interval)

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_START, home_assistant_startup
        )

    async def _update_power_sensor(self, trigger_entity_id: str, state) -> bool:
        """Update power sensor based on new dependant entity state."""
        if (
            state is None
            or state.state == STATE_UNKNOWN
            or (not self._ignore_unavailable_state and state.state == STATE_UNAVAILABLE)
        ):
            _LOGGER.debug("%s: Source entity has an invalid state, setting power sensor to unavailable", trigger_entity_id)
            self._power = None
            self.async_write_ha_state()
            return False
        
        self._power = await self.calculate_power(state)

        _LOGGER.debug(
            '%s: State changed to "%s". Power:%s',
            state.entity_id,
            state.state,
            self._power,
        )

        if self._power is None:
            self.async_write_ha_state()
            return False

        self._power = round(self._power, self._rounding_digits)

        self.async_write_ha_state()
        return True

    async def calculate_power(self, state) -> Optional[Decimal]:
        """Calculate power consumption using configured strategy."""

        if state.state in OFF_STATES:
            standby_power = 0
            if self._standby_power:
                standby_power = self._standby_power
            elif self._power_calculator.can_calculate_standby():
                standby_power = await self._power_calculator.calculate(state)

            if self._multiply_factor_standby and self._multiply_factor:
                standby_power *= self._multiply_factor
            return Decimal(standby_power)

        power = await self._power_calculator.calculate(state)
        if power is None:
            return None

        if self._multiply_factor:
            power *= Decimal(self._multiply_factor)

        return Decimal(power)

    @property
    def source_entity(self):
        """The source entity this power sensor calculates power for."""
        return self._source_entity

    @property
    def extra_state_attributes(self):
        """Return entity state attributes."""
        return {
            ATTR_CALCULATION_MODE: self._calculation_mode,
            ATTR_INTEGRATION: DOMAIN,
            ATTR_SOURCE_ENTITY: self._source_entity,
            ATTR_SOURCE_DOMAIN: self._source_domain,
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._power

    @property
    def available(self):
        """Return True if entity is available."""
        return self._power is not None


class RealPowerSensor(PowerSensor):
    """Contains a reference to a existing real power sensor entity"""

    def __init__(self, entity_id: str, device_id: str = None, unique_id: str = None):
        self._entity_id = entity_id
        self._device_id = device_id
        self._unique_id = unique_id

    @property
    def entity_id(self) -> str:
        """Return the name of the sensor."""
        return self._entity_id

    @property
    def device_id(self) -> str:
        """Return the device_id of the sensor."""
        return self._device_id

    @property
    def unique_id(self) -> str:
        """Return the unique_id of the sensor."""
        return self._unique_id
