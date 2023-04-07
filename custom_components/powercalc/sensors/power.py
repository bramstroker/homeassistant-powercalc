from __future__ import annotations

import logging
from decimal import Decimal, DecimalException
from typing import Any, cast

import homeassistant.helpers.entity_registry as er
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    POWER_WATT,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, State, callback
from homeassistant.helpers import start
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import (
    TrackTemplate,
    async_call_later,
    async_track_state_change_event,
    async_track_template_result,
    async_track_time_interval,
)
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import DiscoveryInfoType, StateType

from ..common import SourceEntity
from ..const import (
    ATTR_CALCULATION_MODE,
    ATTR_ENERGY_SENSOR_ENTITY_ID,
    ATTR_INTEGRATION,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_DELAY,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISABLE_STANDBY_POWER,
    CONF_FIXED,
    CONF_FORCE_UPDATE_FREQUENCY,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_LINEAR,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SLEEP_POWER,
    CONF_STANDBY_POWER,
    CONF_UNAVAILABLE_POWER,
    CONF_WLED,
    DATA_CALCULATOR_FACTORY,
    DISCOVERY_POWER_PROFILE,
    DOMAIN,
    DUMMY_ENTITY_ID,
    OFF_STATES,
    CalculationStrategy,
)
from ..discovery import autodiscover_model
from ..errors import ModelNotSupported, StrategyConfigurationError, UnsupportedStrategy
from ..power_profile.factory import get_power_profile
from ..power_profile.power_profile import PowerProfile, SubProfileSelector
from ..strategy.factory import PowerCalculatorStrategyFactory
from ..strategy.strategy_interface import PowerCalculationStrategyInterface
from .abstract import (
    BaseEntity,
    generate_power_sensor_entity_id,
    generate_power_sensor_name,
)

_LOGGER = logging.getLogger(__name__)


async def create_power_sensor(
    hass: HomeAssistant,
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
    hass: HomeAssistant,
    sensor_config: dict,
    source_entity: SourceEntity,
    discovery_info: DiscoveryInfoType | None = None,
) -> VirtualPowerSensor:
    """Create the power sensor entity"""

    power_profile = None
    try:
        # When the user did not manually configure a model and a model was auto discovered we can load it.

        if (
            discovery_info
            and sensor_config.get(CONF_MODEL) is None
            and discovery_info.get(DISCOVERY_POWER_PROFILE)
        ):
            power_profile = discovery_info.get(DISCOVERY_POWER_PROFILE)
        else:
            try:
                model_info = await autodiscover_model(hass, source_entity.entity_entry)
                power_profile = await get_power_profile(
                    hass, sensor_config, model_info=model_info
                )
                # Check if this power profile supports automatic sub profile selection
                # If so, trigger an initial selection of the sub profile bases on source entity state
                if power_profile and power_profile.sub_profile_select:
                    sub_profile_selector = SubProfileSelector(
                        hass, power_profile, source_entity
                    )
                    power_profile.select_sub_profile(
                        sub_profile_selector.select_sub_profile(
                            State(source_entity.entity_id, STATE_UNKNOWN)
                        )
                    )
            except ModelNotSupported as err:
                if not is_fully_configured(sensor_config):
                    _LOGGER.error(
                        "%s: Skipping sensor setup %s", source_entity.entity_id, err
                    )
                    raise err

        if power_profile and power_profile.sensor_config != {}:
            sensor_config.update(power_profile.sensor_config)

        name = generate_power_sensor_name(
            sensor_config, sensor_config.get(CONF_NAME), source_entity
        )
        unique_id = sensor_config.get(CONF_UNIQUE_ID) or source_entity.unique_id
        entity_id = generate_power_sensor_entity_id(
            hass, sensor_config, source_entity, unique_id=unique_id
        )
        entity_category = sensor_config.get(CONF_POWER_SENSOR_CATEGORY)

        strategy = select_calculation_strategy(sensor_config, power_profile)

        calculation_strategy_factory: PowerCalculatorStrategyFactory = hass.data[
            DOMAIN
        ][DATA_CALCULATOR_FACTORY]
        calculation_strategy = calculation_strategy_factory.create(
            sensor_config, strategy, power_profile, source_entity
        )
        await calculation_strategy.validate_config()
    except (StrategyConfigurationError, UnsupportedStrategy) as err:
        _LOGGER.error(
            "%s: Skipping sensor setup: %s",
            source_entity.entity_id,
            err,
        )
        raise err

    standby_power = Decimal(0)
    standby_power_on = Decimal(0)
    if not sensor_config.get(CONF_DISABLE_STANDBY_POWER):
        if sensor_config.get(CONF_STANDBY_POWER):
            standby_power = Decimal(sensor_config.get(CONF_STANDBY_POWER))
        elif power_profile is not None:
            standby_power = Decimal(power_profile.standby_power)
            standby_power_on = Decimal(power_profile.standby_power_on)

    if (
        CONF_CALCULATION_ENABLED_CONDITION not in sensor_config
        and power_profile is not None
        and power_profile.calculation_enabled_condition
    ):
        sensor_config[
            CONF_CALCULATION_ENABLED_CONDITION
        ] = power_profile.calculation_enabled_condition

    _LOGGER.debug(
        "Creating power sensor (entity_id=%s entity_category=%s, sensor_name=%s strategy=%s manufacturer=%s model=%s standby_power=%s unique_id=%s)",
        source_entity.entity_id,
        entity_category,
        name,
        calculation_strategy.__class__.__name__,
        power_profile.manufacturer if power_profile else "",
        power_profile.model if power_profile else "",
        round(standby_power, 2),
        unique_id,
    )

    return VirtualPowerSensor(
        power_calculator=calculation_strategy,
        calculation_strategy=strategy,
        entity_id=entity_id,
        entity_category=entity_category,
        name=name,
        source_entity=source_entity,
        unique_id=unique_id,
        standby_power=standby_power,
        standby_power_on=standby_power_on,
        update_frequency=sensor_config.get(CONF_FORCE_UPDATE_FREQUENCY),
        multiply_factor=sensor_config.get(CONF_MULTIPLY_FACTOR),
        multiply_factor_standby=sensor_config.get(CONF_MULTIPLY_FACTOR_STANDBY),
        ignore_unavailable_state=sensor_config.get(CONF_IGNORE_UNAVAILABLE_STATE)
        or False,
        rounding_digits=sensor_config.get(CONF_POWER_SENSOR_PRECISION),
        sensor_config=sensor_config,
        power_profile=power_profile,
    )


async def create_real_power_sensor(
    hass: HomeAssistant, sensor_config: dict
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


def select_calculation_strategy(
    config: dict, power_profile: PowerProfile | None
) -> CalculationStrategy:
    """Select the calculation strategy"""
    config_mode = config.get(CONF_MODE)
    if config_mode:
        return config_mode

    if config.get(CONF_LINEAR):
        return CalculationStrategy.LINEAR

    if config.get(CONF_FIXED):
        return CalculationStrategy.FIXED

    if config.get(CONF_WLED):
        return CalculationStrategy.WLED

    if power_profile:
        return power_profile.calculation_strategy

    raise UnsupportedStrategy(
        "Cannot select a strategy (LINEAR, FIXED or LUT, WLED), supply it in the config. See the readme"
    )


def is_fully_configured(config) -> bool:
    if config.get(CONF_FIXED):
        return True
    if config.get(CONF_LINEAR):
        return True
    if config.get(CONF_WLED):
        return True
    return False


class PowerSensor(BaseEntity):
    """Class which all power sensors should extend from"""

    pass


class VirtualPowerSensor(SensorEntity, PowerSensor):
    """Virtual power sensor"""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = POWER_WATT
    _attr_should_poll: bool = False

    def __init__(
        self,
        power_calculator: PowerCalculationStrategyInterface,
        calculation_strategy: CalculationStrategy,
        entity_id: str,
        entity_category: str,
        name: str,
        source_entity: SourceEntity,
        unique_id: str,
        standby_power: Decimal,
        standby_power_on: Decimal,
        update_frequency,
        multiply_factor: float | None,
        multiply_factor_standby: bool,
        ignore_unavailable_state: bool,
        rounding_digits: int,
        sensor_config: dict,
        power_profile: PowerProfile | None,
    ):
        """Initialize the sensor."""
        self._power_calculator = power_calculator
        self._calculation_mode = calculation_strategy
        self._source_entity = source_entity
        self._attr_name = name
        self._power = None
        self._standby_power = standby_power
        self._standby_power_on = standby_power_on
        self._attr_force_update = True
        self._attr_unique_id = unique_id
        self._update_frequency = update_frequency
        self._multiply_factor = multiply_factor
        self._multiply_factor_standby = multiply_factor_standby
        self._ignore_unavailable_state = ignore_unavailable_state
        self._rounding_digits = rounding_digits
        self.entity_id = entity_id
        self._sensor_config = sensor_config
        self._track_entities: list = []
        self._sleep_power_timer: CALLBACK_TYPE | None = None
        if entity_category:
            self._attr_entity_category = EntityCategory(entity_category)
        if not sensor_config.get(CONF_DISABLE_EXTENDED_ATTRIBUTES):
            self._attr_extra_state_attributes = {
                ATTR_CALCULATION_MODE: calculation_strategy,
                ATTR_INTEGRATION: DOMAIN,
                ATTR_SOURCE_ENTITY: source_entity.entity_id,
                ATTR_SOURCE_DOMAIN: source_entity.domain,
            }
        self._power_profile = power_profile
        self._sub_profile_selector: SubProfileSelector | None = None
        if (
            not self._ignore_unavailable_state
            and self._sensor_config.get(CONF_UNAVAILABLE_POWER) is not None
        ):
            self._ignore_unavailable_state = True

    async def async_added_to_hass(self):
        """Register callbacks."""
        await super().async_added_to_hass()

        async def appliance_state_listener(event):
            """Handle for state changes for dependent sensors."""
            new_state = event.data.get("new_state")

            await self._update_power_sensor(self._source_entity.entity_id, new_state)

        async def template_change_listener(*args):
            state = self.hass.states.get(self._source_entity.entity_id)
            await self._update_power_sensor(self._source_entity.entity_id, state)

        async def initial_update(event):
            for entity_id in self._track_entities:
                new_state = self.hass.states.get(entity_id)

                await self._update_power_sensor(entity_id, new_state)

        """Add listeners and get initial state."""
        entities_to_track = self._power_calculator.get_entities_to_track()

        track_entities = [
            entity for entity in entities_to_track if isinstance(entity, str)
        ]
        if not track_entities:
            track_entities = [self._source_entity.entity_id]

        if self._power_profile:
            self._sub_profile_selector = SubProfileSelector(
                self.hass, self._power_profile, self._source_entity
            )
            track_entities.extend(self._sub_profile_selector.get_tracking_entities())

        self._track_entities = track_entities

        async_track_state_change_event(
            self.hass, track_entities, appliance_state_listener
        )

        track_templates = [
            template
            for template in entities_to_track
            if isinstance(template, TrackTemplate)
        ]
        if track_templates:
            async_track_template_result(
                self.hass,
                track_templates=track_templates,
                action=template_change_listener,
            )

        self.async_on_remove(start.async_at_start(self.hass, initial_update))

        @callback
        def async_update(event_time=None):
            """Update the entity."""
            self.async_schedule_update_ha_state(True)

        async_track_time_interval(self.hass, async_update, self._update_frequency)

    async def _update_power_sensor(
        self, trigger_entity_id: str, state: State | None
    ) -> bool:
        """Update power sensor based on new dependant entity state."""

        if self._sleep_power_timer:
            self._sleep_power_timer()
            self._sleep_power_timer = None

        if self.source_entity == DUMMY_ENTITY_ID:
            state = State(self.source_entity, STATE_ON)

        if not self._has_valid_state(state):
            _LOGGER.debug(
                "%s: Source entity has an invalid state, setting power sensor to unavailable",
                trigger_entity_id,
            )
            self._power = None
            self.async_write_ha_state()
            return False

        self._switch_sub_profile_dynamically(state)
        self._power = await self.calculate_power(state)

        if self._power is not None:
            self._power = round(self._power, self._rounding_digits)

        _LOGGER.debug(
            '%s: State changed to "%s". Power:%s',
            state.entity_id,
            state.state,
            self._power,
        )

        if self._power is None:
            self.async_write_ha_state()
            return False

        self.async_write_ha_state()
        return True

    def _has_valid_state(self, state: State | None) -> bool:
        """Check if the state is valid, we can use it for power calculation"""
        if self.source_entity == DUMMY_ENTITY_ID:
            return True

        if state is None:
            return False

        if state.state == STATE_UNKNOWN:
            return False

        if not self._ignore_unavailable_state and state.state == STATE_UNAVAILABLE:
            return False

        return True

    async def calculate_power(self, state: State) -> Decimal | None:
        """Calculate power consumption using configured strategy."""

        entity_state = state
        if state.entity_id != self._source_entity.entity_id:
            entity_state = self.hass.states.get(self._source_entity.entity_id)

        unavailable_power = self._sensor_config.get(CONF_UNAVAILABLE_POWER)
        if entity_state.state == STATE_UNAVAILABLE and unavailable_power is not None:
            return Decimal(unavailable_power)

        is_calculation_enabled = await self.is_calculation_enabled()
        if entity_state.state in OFF_STATES or not is_calculation_enabled:
            return await self.calculate_standby_power(entity_state)

        power = await self._power_calculator.calculate(entity_state)
        if power is None:
            return None

        if self._multiply_factor:
            power *= Decimal(self._multiply_factor)

        if self._standby_power_on:
            standby_power = self._standby_power_on
            if self._multiply_factor_standby and self._multiply_factor:
                standby_power *= Decimal(self._multiply_factor)
            power += standby_power

        try:
            return Decimal(power)
        except DecimalException:
            _LOGGER.error(
                f"{state.entity_id}: Could not convert value '{power}' to decimal"
            )
            return None

    def _switch_sub_profile_dynamically(self, state: State) -> None:
        """
        Dynamically select a different sub profile depending on the entity state or attributes
        Uses SubProfileSelect class which contains all the matching logic
        """
        if not self._power_profile or not self._power_profile.sub_profile_select:
            return

        self._power_profile.select_sub_profile(
            self._sub_profile_selector.select_sub_profile(state)
        )
        self._standby_power = self._power_profile.standby_power
        self._standby_power_on = self._power_profile.standby_power_on

    async def calculate_standby_power(self, state: State) -> Decimal:
        """Calculate the power of the device in OFF state"""
        sleep_power: dict[str, Any] = self._sensor_config.get(CONF_SLEEP_POWER)
        if sleep_power:
            delay = sleep_power.get(CONF_DELAY)

            @callback
            def _update_sleep_power(_):
                power = Decimal(sleep_power.get(CONF_POWER))
                if self._multiply_factor_standby and self._multiply_factor:
                    power *= Decimal(self._multiply_factor)
                self._power = round(power, self._rounding_digits)
                self.async_write_ha_state()

            self._sleep_power_timer = async_call_later(
                self.hass, delay, _update_sleep_power
            )

        standby_power = self._standby_power
        if self._power_calculator.can_calculate_standby():
            standby_power = await self._power_calculator.calculate(state)

        if self._multiply_factor_standby and self._multiply_factor:
            standby_power *= Decimal(self._multiply_factor)
        return Decimal(standby_power)

    async def is_calculation_enabled(self) -> bool:
        if CONF_CALCULATION_ENABLED_CONDITION not in self._sensor_config:
            return True

        template = self._sensor_config.get(CONF_CALCULATION_ENABLED_CONDITION)
        if isinstance(template, str):
            template = template.replace("[[entity]]", self.source_entity)
            template = Template(template)

        template.hass = self.hass
        return bool(template.async_render())

    @property
    def source_entity(self) -> str:
        """The source entity this power sensor calculates power for."""
        return self._source_entity.entity_id

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return cast(StateType, self._power)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._power is not None

    def set_energy_sensor_attribute(self, entity_id: str):
        """Set the energy sensor on the state attributes"""
        if self._sensor_config.get(CONF_DISABLE_EXTENDED_ATTRIBUTES):
            return
        self._attr_extra_state_attributes.update(
            {ATTR_ENERGY_SENSOR_ENTITY_ID: entity_id}
        )


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
