from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import homeassistant.helpers.entity_registry as er
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    MATCH_ALL,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPower,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import start
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import (
    EventStateChangedData,
    TrackTemplate,
    async_call_later,
    async_track_state_change_event,
    async_track_template_result,
    async_track_time_interval,
)
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType, StateType

from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    ATTR_CALCULATION_MODE,
    ATTR_ENERGY_SENSOR_ENTITY_ID,
    ATTR_INTEGRATION,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_COMPOSITE,
    CONF_DELAY,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISABLE_STANDBY_POWER,
    CONF_FIXED,
    CONF_FORCE_UPDATE_FREQUENCY,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_LINEAR,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_PLAYBOOK,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SLEEP_POWER,
    CONF_STANDBY_POWER,
    CONF_UNAVAILABLE_POWER,
    CONF_WLED,
    DATA_CALCULATOR_FACTORY,
    DATA_DISCOVERY_MANAGER,
    DATA_STANDBY_POWER_SENSORS,
    DOMAIN,
    DUMMY_ENTITY_ID,
    OFF_STATES,
    SIGNAL_POWER_SENSOR_STATE_CHANGE,
    CalculationStrategy,
)
from custom_components.powercalc.discovery import DiscoveryManager
from custom_components.powercalc.errors import (
    ModelNotSupportedError,
    StrategyConfigurationError,
    UnsupportedStrategyError,
)
from custom_components.powercalc.helpers import evaluate_power
from custom_components.powercalc.power_profile.factory import get_power_profile
from custom_components.powercalc.power_profile.power_profile import (
    PowerProfile,
    SubProfileSelectConfig,
    SubProfileSelector,
)
from custom_components.powercalc.strategy.factory import PowerCalculatorStrategyFactory
from custom_components.powercalc.strategy.playbook import PlaybookStrategy
from custom_components.powercalc.strategy.selector import detect_calculation_strategy
from custom_components.powercalc.strategy.strategy_interface import (
    PowerCalculationStrategyInterface,
)

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
    config_entry: ConfigEntry | None,
) -> PowerSensor:
    """Create the power sensor based on powercalc sensor configuration."""
    if CONF_POWER_SENSOR_ID in sensor_config:
        # Use an existing power sensor, only create energy sensors / utility meters
        return await create_real_power_sensor(hass, sensor_config)

    return await create_virtual_power_sensor(
        hass,
        sensor_config,
        source_entity,
        config_entry,
    )


async def create_virtual_power_sensor(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity,
    config_entry: ConfigEntry | None,
) -> VirtualPowerSensor:
    """Create the power sensor entity."""
    try:
        power_profile = await _get_power_profile(hass, sensor_config, source_entity)
        if power_profile:
            if power_profile.sensor_config != {}:
                sensor_config.update(power_profile.sensor_config)
            if CONF_CALCULATION_ENABLED_CONDITION not in sensor_config and power_profile.calculation_enabled_condition:
                sensor_config[CONF_CALCULATION_ENABLED_CONDITION] = power_profile.calculation_enabled_condition

        name = generate_power_sensor_name(
            sensor_config,
            sensor_config.get(CONF_NAME),
            source_entity,
        )
        unique_id = sensor_config.get(CONF_UNIQUE_ID) or source_entity.unique_id
        entity_id = generate_power_sensor_entity_id(
            hass,
            sensor_config,
            source_entity,
            unique_id=unique_id,
        )
        entity_category: str | None = sensor_config.get(CONF_POWER_SENSOR_CATEGORY) or None
        strategy = detect_calculation_strategy(sensor_config, power_profile)
        calculation_strategy_factory: PowerCalculatorStrategyFactory = hass.data[DOMAIN][DATA_CALCULATOR_FACTORY]

        standby_power, standby_power_on = _get_standby_power(sensor_config, power_profile)

        _LOGGER.debug(
            "Creating power sensor (entity_id=%s entity_category=%s, sensor_name=%s strategy=%s manufacturer=%s model=%s unique_id=%s)",
            source_entity.entity_id,
            entity_category,
            name,
            strategy,
            power_profile.manufacturer if power_profile else "",
            power_profile.model if power_profile else "",
            unique_id,
        )

        power_sensor = VirtualPowerSensor(
            hass=hass,
            calculation_strategy_factory=calculation_strategy_factory,
            calculation_strategy=strategy,
            entity_id=entity_id,
            entity_category=entity_category,
            name=name,
            source_entity=source_entity,
            unique_id=unique_id,
            standby_power=standby_power,
            standby_power_on=standby_power_on,
            sensor_config=sensor_config,
            power_profile=power_profile,
            config_entry=config_entry,
        )
        await power_sensor.validate()
        return power_sensor

    except (StrategyConfigurationError, UnsupportedStrategyError) as err:
        _LOGGER.error(
            "%s: Skipping sensor setup: %s",
            source_entity.entity_id,
            err,
        )
        raise err


async def _get_power_profile(
    hass: HomeAssistant,
    sensor_config: ConfigType,
    source_entity: SourceEntity,
) -> PowerProfile | None:
    """Retrieve the power profile based on auto-discovery or manual configuration."""
    discovery_manager: DiscoveryManager = hass.data[DOMAIN][DATA_DISCOVERY_MANAGER]
    power_profile = None
    if not is_manually_configured(sensor_config):
        try:
            model_info = await discovery_manager.autodiscover_model(source_entity.entity_entry)
            power_profile = await get_power_profile(
                hass,
                sensor_config,
                model_info=model_info,
            )
            if power_profile and power_profile.sub_profile_select:
                await _select_sub_profile(hass, power_profile, power_profile.sub_profile_select, source_entity)
        except ModelNotSupportedError as err:
            if not is_fully_configured(sensor_config):
                _LOGGER.error(
                    "%s: Skipping sensor setup: %s",
                    source_entity.entity_id,
                    err,
                )
                raise err
    return power_profile


async def _select_sub_profile(
    hass: HomeAssistant,
    power_profile: PowerProfile,
    sub_profile: SubProfileSelectConfig,
    source_entity: SourceEntity,
) -> None:
    """Select the appropriate sub-profile based on the source entity's state."""
    sub_profile_selector = SubProfileSelector(
        hass,
        sub_profile,
        source_entity,
    )
    await power_profile.select_sub_profile(
        sub_profile_selector.select_sub_profile(
            State(source_entity.entity_id, STATE_UNKNOWN),
        ),
    )


def _get_standby_power(
    sensor_config: ConfigType,
    power_profile: PowerProfile | None,
) -> tuple[Template | Decimal, Decimal]:
    """Retrieve standby power settings from sensor config or power profile."""
    standby_power: Template | Decimal = Decimal(0)
    standby_power_on = Decimal(0)

    if not sensor_config.get(CONF_DISABLE_STANDBY_POWER):
        if sensor_config.get(CONF_STANDBY_POWER) is not None:
            standby_power = sensor_config.get(CONF_STANDBY_POWER)  # type: ignore
            if not isinstance(standby_power, Template):
                standby_power = Decimal(standby_power)
        elif power_profile is not None:
            standby_power = Decimal(power_profile.standby_power)
            standby_power_on = Decimal(power_profile.standby_power_on)

    return standby_power, standby_power_on


async def create_real_power_sensor(
    hass: HomeAssistant,
    sensor_config: dict,
) -> RealPowerSensor:
    """Create reference to an existing power sensor."""
    power_sensor_id = sensor_config.get(CONF_POWER_SENSOR_ID)
    unique_id = sensor_config.get(CONF_UNIQUE_ID)
    device_id = None
    unit_of_measurement = None
    ent_reg = er.async_get(hass)
    entity_entry = ent_reg.async_get(power_sensor_id)  # type: ignore
    if entity_entry:
        if not unique_id:
            unique_id = entity_entry.unique_id
        device_id = entity_entry.device_id
        unit_of_measurement = entity_entry.unit_of_measurement

    return RealPowerSensor(
        entity_id=power_sensor_id,  # type: ignore
        device_id=device_id,
        unique_id=unique_id,
        unit_of_measurement=unit_of_measurement,
    )


def is_manually_configured(sensor_config: ConfigType) -> bool:
    """Check if the user manually configured the sensor.
    We need to skip loading a power profile to make.
    """
    if CONF_MODEL in sensor_config:
        return False
    return any(key in sensor_config for key in [CONF_LINEAR, CONF_FIXED, CONF_PLAYBOOK, CONF_COMPOSITE])


def is_fully_configured(config: ConfigType) -> bool:
    return any(key in config for key in [CONF_LINEAR, CONF_WLED, CONF_FIXED, CONF_PLAYBOOK])


class PowerSensor(BaseEntity):
    """Class which all power sensors should extend from."""


class VirtualPowerSensor(SensorEntity, PowerSensor):
    """Virtual power sensor."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_should_poll: bool = False
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(
        self,
        hass: HomeAssistant,
        calculation_strategy_factory: PowerCalculatorStrategyFactory,
        calculation_strategy: CalculationStrategy,
        entity_id: str,
        entity_category: str | None,
        name: str,
        source_entity: SourceEntity,
        unique_id: str | None,
        standby_power: Decimal | Template,
        standby_power_on: Decimal,
        sensor_config: dict,
        power_profile: PowerProfile | None,
        config_entry: ConfigEntry | None,
    ) -> None:
        """Initialize the sensor."""
        self._calculation_strategy = calculation_strategy
        self._calculation_enabled_condition: Template | None = None
        self._source_entity = source_entity
        self._attr_name = name
        self._power: Decimal | None = None
        self._standby_power = standby_power
        self._standby_power_on = standby_power_on
        self._attr_force_update = True
        self._attr_unique_id = unique_id
        self._update_frequency: timedelta = sensor_config.get(CONF_FORCE_UPDATE_FREQUENCY)  # type: ignore
        self._multiply_factor = sensor_config.get(CONF_MULTIPLY_FACTOR)
        self._multiply_factor_standby = bool(sensor_config.get(CONF_MULTIPLY_FACTOR_STANDBY, False))
        self._ignore_unavailable_state = bool(sensor_config.get(CONF_IGNORE_UNAVAILABLE_STATE, False))
        self._rounding_digits = int(sensor_config.get(CONF_POWER_SENSOR_PRECISION))  # type: ignore
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
        if not self._ignore_unavailable_state and self._sensor_config.get(CONF_UNAVAILABLE_POWER) is not None:
            self._ignore_unavailable_state = True
        self._standby_sensors: dict = hass.data[DOMAIN][DATA_STANDBY_POWER_SENSORS]
        self.calculation_strategy_factory = calculation_strategy_factory
        self._strategy_instance: PowerCalculationStrategyInterface | None = None
        self._config_entry = config_entry

    async def validate(self) -> None:
        await self.ensure_strategy_instance()
        assert self._strategy_instance is not None
        await self._strategy_instance.validate_config()

    async def ensure_strategy_instance(self, recreate: bool = False) -> None:
        if self._strategy_instance is None or recreate:
            self._strategy_instance = await self.calculation_strategy_factory.create(
                self._sensor_config,
                self._calculation_strategy,
                self._power_profile,
                self._source_entity,
            )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        await super().async_added_to_hass()
        await self.ensure_strategy_instance()
        assert self._strategy_instance is not None
        self.init_calculation_enabled_condition()

        async def appliance_state_listener(event: Event[EventStateChangedData]) -> None:
            """Handle for state changes for dependent sensors."""
            new_state = event.data.get("new_state")
            await self._handle_source_entity_state_change(
                self._source_entity.entity_id,
                new_state,
            )
            async_dispatcher_send(self.hass, SIGNAL_POWER_SENSOR_STATE_CHANGE)

        async def template_change_listener(*_: Any) -> None:  # noqa: ANN401
            state = self.hass.states.get(self._source_entity.entity_id)
            await self._handle_source_entity_state_change(
                self._source_entity.entity_id,
                state,
            )
            async_dispatcher_send(self.hass, SIGNAL_POWER_SENSOR_STATE_CHANGE)

        async def initial_update(hass: HomeAssistant) -> None:
            if self._strategy_instance:
                await self._strategy_instance.on_start(hass)
            for entity_id in self._track_entities:
                new_state = self.hass.states.get(entity_id)
                await self._handle_source_entity_state_change(
                    entity_id,
                    new_state,
                )
                async_dispatcher_send(self.hass, SIGNAL_POWER_SENSOR_STATE_CHANGE)

        """Add listeners and get initial state."""
        entities_to_track = self._strategy_instance.get_entities_to_track()

        track_entities = [entity for entity in entities_to_track if isinstance(entity, str)]
        if not track_entities:
            track_entities = [self._source_entity.entity_id]

        if self._power_profile and self._power_profile.sub_profile_select:
            self._sub_profile_selector = SubProfileSelector(
                self.hass,
                self._power_profile.sub_profile_select,
                self._source_entity,
            )
            track_entities.extend(self._sub_profile_selector.get_tracking_entities())

        self._track_entities = track_entities

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                track_entities,
                appliance_state_listener,
            ),
        )

        track_templates = [template for template in entities_to_track if isinstance(template, TrackTemplate)]
        if isinstance(self._standby_power, Template):
            self._standby_power.hass = self.hass
            track_templates.append(TrackTemplate(self._standby_power, None, None))
        if self._calculation_enabled_condition:
            track_templates.append(
                TrackTemplate(self._calculation_enabled_condition, None, None),
            )
        if track_templates:
            async_track_template_result(
                self.hass,
                track_templates=track_templates,
                action=template_change_listener,
            )

        self.async_on_remove(start.async_at_start(self.hass, initial_update))

        if isinstance(self._strategy_instance, PlaybookStrategy):
            self._strategy_instance.set_update_callback(self._update_power_sensor)

        @callback
        def async_update(__: datetime | None = None) -> None:
            """Update the entity."""
            self.async_schedule_update_ha_state(True)

        async_track_time_interval(self.hass, async_update, self._update_frequency)

    def init_calculation_enabled_condition(self) -> None:
        if CONF_CALCULATION_ENABLED_CONDITION not in self._sensor_config:
            return

        template: Template | str = self._sensor_config.get(CONF_CALCULATION_ENABLED_CONDITION)  # type: ignore
        if isinstance(template, str):
            template = template.replace("[[entity]]", self.source_entity)
            template = Template(template, self.hass)

        self._calculation_enabled_condition = template

    async def _handle_source_entity_state_change(
        self,
        trigger_entity_id: str,
        state: State | None,
    ) -> None:
        """Update power sensor based on new dependant entity state."""
        self._standby_sensors.pop(self.entity_id, None)
        if self._sleep_power_timer:
            self._sleep_power_timer()
            self._sleep_power_timer = None

        if self.source_entity == DUMMY_ENTITY_ID:
            state = State(self.source_entity, STATE_ON)

        if not state or not self._has_valid_state(state):
            _LOGGER.debug(
                "%s: Source entity has an invalid state, setting power sensor to unavailable",
                trigger_entity_id,
            )
            self._power = None
            self.async_write_ha_state()
            return

        await self._switch_sub_profile_dynamically(state)
        self._power = await self.calculate_power(state)

        if self._power is not None:
            self._power = round(self._power, self._rounding_digits)

        _LOGGER.debug(
            '%s: State changed to "%s". Power:%s',
            state.entity_id,
            state.state,
            self._power,
        )

        self.async_write_ha_state()

    @callback
    def _update_power_sensor(self, power: Decimal) -> None:
        self._power = power
        if self._multiply_factor:
            self._power *= Decimal(self._multiply_factor)
        self._power = round(self._power, self._rounding_digits)
        self.async_write_ha_state()

    def _has_valid_state(self, state: State) -> bool:
        """Check if the state is valid, we can use it for power calculation."""
        if self.source_entity == DUMMY_ENTITY_ID:
            return True

        return self._ignore_unavailable_state or state.state not in [STATE_UNAVAILABLE, STATE_UNKNOWN]

    async def calculate_power(self, state: State) -> Decimal | None:
        """Calculate power consumption using configured strategy."""
        entity_state = state
        if (
            self._calculation_strategy != CalculationStrategy.MULTI_SWITCH
            and state.entity_id != self._source_entity.entity_id
            and (entity_state := self.hass.states.get(self._source_entity.entity_id)) is None
        ):
            return None

        unavailable_power = self._sensor_config.get(CONF_UNAVAILABLE_POWER)
        if entity_state.state == STATE_UNAVAILABLE and unavailable_power is not None:
            return Decimal(unavailable_power)

        is_calculation_enabled = await self.is_calculation_enabled()
        if entity_state.state in OFF_STATES or not is_calculation_enabled:
            if isinstance(self._strategy_instance, PlaybookStrategy):
                await self._strategy_instance.stop_playbook()
            standby_power = await self.calculate_standby_power(entity_state)
            self._standby_sensors[self.entity_id] = standby_power
            return standby_power

        assert self._strategy_instance is not None
        power = await self._strategy_instance.calculate(entity_state)
        if power is None:
            return None

        if self._multiply_factor:
            power *= Decimal(self._multiply_factor)

        if self._standby_power_on:
            standby_power = self._standby_power_on
            if self._multiply_factor_standby and self._multiply_factor:
                standby_power *= Decimal(self._multiply_factor)
            power += standby_power

        return Decimal(power)

    async def _switch_sub_profile_dynamically(self, state: State) -> None:
        """Dynamically select a different sub profile depending on the entity state or attributes
        Uses SubProfileSelect class which contains all the matching logic.
        """
        if not self._power_profile or not self._power_profile.sub_profile_select or not self._sub_profile_selector:
            return

        new_profile = self._sub_profile_selector.select_sub_profile(state)
        await self._select_new_sub_profile(new_profile)

    async def _select_new_sub_profile(self, profile: str) -> None:
        if not self._power_profile or self._power_profile.sub_profile == profile:
            return

        await self._power_profile.select_sub_profile(profile)
        self._standby_power = Decimal(self._power_profile.standby_power)
        self._standby_power_on = Decimal(self._power_profile.standby_power_on)
        await self.ensure_strategy_instance(True)

    async def calculate_standby_power(self, state: State) -> Decimal:
        """Calculate the power of the device in OFF state."""
        assert self._strategy_instance is not None
        sleep_power: ConfigType = self._sensor_config.get(CONF_SLEEP_POWER)  # type: ignore
        if sleep_power:
            delay = sleep_power.get(CONF_DELAY)

            @callback
            def _update_sleep_power(*_: Any) -> None:  # noqa: ANN401
                power = Decimal(sleep_power.get(CONF_POWER) or 0)
                if self._multiply_factor_standby and self._multiply_factor:
                    power *= Decimal(self._multiply_factor)
                self._power = round(power, self._rounding_digits)
                self.async_write_ha_state()

            self._sleep_power_timer = async_call_later(
                self.hass,
                delay,  # type: ignore
                _update_sleep_power,
            )

        standby_power = self._standby_power
        if self._strategy_instance.can_calculate_standby():
            standby_power = await self._strategy_instance.calculate(state) or Decimal(0)

        evaluated = await evaluate_power(standby_power)
        if evaluated is None:
            evaluated = Decimal(0)
        standby_power = evaluated

        if self._multiply_factor_standby and self._multiply_factor:
            standby_power *= Decimal(self._multiply_factor)

        return standby_power

    async def is_calculation_enabled(self) -> bool:
        template = self._calculation_enabled_condition
        if not template:
            return True

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

    def set_energy_sensor_attribute(self, entity_id: str) -> None:
        """Set the energy sensor on the state attributes."""
        if self._sensor_config.get(CONF_DISABLE_EXTENDED_ATTRIBUTES):
            return
        self._attr_extra_state_attributes.update(
            {ATTR_ENERGY_SENSOR_ENTITY_ID: entity_id},
        )

    async def async_activate_playbook(self, playbook_id: str) -> None:
        """Active a playbook"""
        strategy_instance = self._ensure_playbook_strategy()
        await strategy_instance.activate_playbook(playbook_id)

    async def async_stop_playbook(self) -> None:
        """Stop an active playbook"""
        strategy_instance = self._ensure_playbook_strategy()
        await strategy_instance.stop_playbook()

    def get_active_playbook(self) -> dict[str, str]:
        """Stop an active playbook"""
        strategy_instance = self._ensure_playbook_strategy()
        playbook = strategy_instance.get_active_playbook()
        if not playbook:
            return {}
        return {"id": playbook.key}

    def _ensure_playbook_strategy(self) -> PlaybookStrategy:
        """Ensure we are dealing with a playbook sensor."""
        assert self._strategy_instance is not None
        if not isinstance(self._strategy_instance, PlaybookStrategy):
            raise HomeAssistantError("supported only playbook enabled sensors")
        return self._strategy_instance

    async def async_switch_sub_profile(self, profile: str) -> None:
        """Switches to a new sub profile"""
        if not self._power_profile or not await self._power_profile.has_sub_profiles or self._power_profile.sub_profile_select:
            raise HomeAssistantError(
                "This is only supported for sensors having sub profiles, and no automatic profile selection",
            )

        if profile not in await self._power_profile.get_sub_profiles():
            raise HomeAssistantError(f"{profile} is not a possible sub profile")

        await self._select_new_sub_profile(profile)

        await self._handle_source_entity_state_change(
            self._source_entity.entity_id,
            self.hass.states.get(self._source_entity.entity_id),
        )

        # Persist the newly selected sub profile on the config entry
        if self._config_entry:
            new_model = f"{self._power_profile.model}/{profile}"
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={**self._config_entry.data, CONF_MODEL: new_model},
            )


class RealPowerSensor(PowerSensor):
    """Contains a reference to an existing real power sensor entity."""

    def __init__(
        self,
        entity_id: str,
        unit_of_measurement: str | None = None,
        device_id: str | None = None,
        unique_id: str | None = None,
    ) -> None:
        self.entity_id = entity_id
        self._device_id = device_id
        self._unique_id = unique_id
        self._attr_unit_of_measurement = unit_of_measurement or UnitOfPower.WATT

    @property
    def device_id(self) -> str | None:
        """Return the device_id of the sensor."""
        return self._device_id

    @property
    def unique_id(self) -> str | None:
        """Return the unique_id of the sensor."""
        return self._unique_id
