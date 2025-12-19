from __future__ import annotations

import asyncio
from copy import copy
from decimal import Decimal
import logging
from typing import Any, cast

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
from homeassistant.helpers import issue_registry as ir, start
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import EntityCategory
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.event import (
    EventStateChangedData,
    TrackTemplate,
    async_call_later,
    async_track_state_change_event,
    async_track_template_result,
)
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType, StateType

from custom_components.powercalc.analytics.analytics import collect_analytics
from custom_components.powercalc.common import SourceEntity
from custom_components.powercalc.const import (
    ATTR_CALCULATION_MODE,
    ATTR_ENERGY_SENSOR_ENTITY_ID,
    ATTR_INTEGRATION,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CALCULATION_STRATEGY_CONF_KEYS,
    CONF_AVAILABILITY_ENTITY,
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_DELAY,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISABLE_STANDBY_POWER,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_SENSOR_PRECISION,
    CONF_SELF_USAGE_INCLUDED,
    CONF_SLEEP_POWER,
    CONF_STANDBY_POWER,
    CONF_UNAVAILABLE_POWER,
    DATA_DISCOVERY_MANAGER,
    DATA_POWER_PROFILES,
    DATA_STANDBY_POWER_SENSORS,
    DATA_STRATEGIES,
    DEFAULT_POWER_SENSOR_PRECISION,
    DOMAIN,
    DUMMY_ENTITY_ID,
    OFF_STATES,
    OFF_STATES_BY_DOMAIN,
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
    DiscoveryBy,
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

            if config_entry and await power_profile.requires_manual_sub_profile_selection and "/" not in sensor_config.get(CONF_MODEL, ""):
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    f"sub_profile_{config_entry.entry_id}",
                    is_fixable=True,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="sub_profile",
                    translation_placeholders={"entry": config_entry.title},
                    data={"config_entry_id": config_entry.entry_id},
                )

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
        calculation_strategy_factory = PowerCalculatorStrategyFactory.get_instance(hass)

        standby_power, standby_power_on = _get_standby_power(sensor_config, power_profile)

        # Collect runtime statistics, which we can publish daily
        a = collect_analytics(hass, config_entry)
        a.inc(DATA_STRATEGIES, strategy)
        a.add(DATA_POWER_PROFILES, power_profile)

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
    if is_manually_configured(sensor_config):
        return None

    power_profile = None
    try:
        model_info = await discovery_manager.extract_model_info_from_device_info(source_entity.entity_entry)
        power_profile = await get_power_profile(
            hass,
            sensor_config,
            source_entity,
            model_info=model_info,
        )
        if power_profile and power_profile.has_sub_profile_select_matchers:
            await _select_sub_profile(hass, power_profile, power_profile.sub_profile_select, source_entity)  # type: ignore
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
    if sensor_config.get(CONF_SELF_USAGE_INCLUDED, False):
        return standby_power, standby_power_on

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
    if CONF_CUSTOM_MODEL_DIRECTORY in sensor_config:
        return False
    if CONF_MODEL in sensor_config:
        return False
    return any(key in sensor_config for key in CALCULATION_STRATEGY_CONF_KEYS)


def is_fully_configured(config: ConfigType) -> bool:
    return any(key in config for key in CALCULATION_STRATEGY_CONF_KEYS)


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
        self._off_states: set[str] = OFF_STATES_BY_DOMAIN.get(source_entity.domain, set()) | OFF_STATES
        self._attr_name = name
        self._power: Decimal | None = None
        self._standby_power = standby_power
        self._standby_power_on = standby_power_on
        self._attr_force_update = True
        self._attr_unique_id = unique_id
        self._multiply_factor = sensor_config.get(CONF_MULTIPLY_FACTOR)
        self._multiply_factor_standby = bool(sensor_config.get(CONF_MULTIPLY_FACTOR_STANDBY, False))
        self._ignore_unavailable_state = bool(sensor_config.get(CONF_IGNORE_UNAVAILABLE_STATE, False))
        self._rounding_digits = int(sensor_config.get(CONF_POWER_SENSOR_PRECISION, DEFAULT_POWER_SENSOR_PRECISION))
        self._attr_suggested_display_precision = self._rounding_digits
        self.entity_id = entity_id
        self._sensor_config = sensor_config
        self._track_entities: set[str] = set()
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
        self._availability_entity: str | None = sensor_config.get(CONF_AVAILABILITY_ENTITY)
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

        async def template_change_listener(*_: Any) -> None:  # noqa: ANN401
            """Handle for state changes for referenced templates."""
            state = self.hass.states.get(self._source_entity.entity_id)
            await self._handle_source_entity_state_change(
                self._source_entity.entity_id,
                state,
            )

        async def initial_update(hass: HomeAssistant) -> None:
            """Calculate initial value and push state"""

            # When using reload service energy sensor became unavailable
            # This is caused because state change listener of energy sensor is registered before power sensor pushes initial update
            # Adding sleep 0 fixes this issue.
            await asyncio.sleep(0)
            if self._strategy_instance:
                await self._strategy_instance.on_start(hass)

            entities = self._track_entities
            if (not entities and self._source_entity.entity_id == DUMMY_ENTITY_ID) or not entities:
                entities.add(DUMMY_ENTITY_ID)
            for entity_id in entities:
                new_state = self.hass.states.get(entity_id) if entity_id != DUMMY_ENTITY_ID else State(entity_id, STATE_ON)
                await self._handle_source_entity_state_change(
                    entity_id,
                    new_state,
                )

        # Add listeners for all tracking entities and templates.
        entities_to_track = self._get_tracking_entities()

        self._track_entities = {e for e in entities_to_track if isinstance(e, str)}
        self.async_on_remove(
            async_track_state_change_event(self.hass, self._track_entities, appliance_state_listener),
        )

        track_templates: list[TrackTemplate] = [e for e in entities_to_track if isinstance(e, TrackTemplate)]
        if track_templates:
            async_track_template_result(self.hass, track_templates=track_templates, action=template_change_listener)

        # Trigger initial update
        self.async_on_remove(start.async_at_start(self.hass, initial_update))

        if hasattr(self._strategy_instance, "set_update_callback"):
            self._strategy_instance.set_update_callback(self._update_power_sensor)

    def _get_tracking_entities(self) -> list[str | TrackTemplate]:
        """Return entities and templates that should be tracked."""
        entities_to_track = copy(self._strategy_instance.get_entities_to_track()) if self._strategy_instance else []

        if self._power_profile and self._power_profile.has_sub_profile_select_matchers:
            self._sub_profile_selector = SubProfileSelector(
                self.hass,
                self._power_profile.sub_profile_select,  # type: ignore
                self._source_entity,
            )
            entities_to_track.extend(self._sub_profile_selector.get_tracking_entities())

        if self._source_entity.entity_id != DUMMY_ENTITY_ID:
            entities_to_track.append(self._source_entity.entity_id)

        if self._availability_entity and self._availability_entity not in entities_to_track:
            entities_to_track.append(self._availability_entity)

        if isinstance(self._standby_power, Template):
            self._standby_power.hass = self.hass
            entities_to_track.append(TrackTemplate(self._standby_power, None, None))

        if self._calculation_enabled_condition:
            entities_to_track.append(TrackTemplate(self._calculation_enabled_condition, None, None))

        return entities_to_track

    def init_calculation_enabled_condition(self) -> None:
        """When a calculation enabled condition is configured, initialize the template."""
        if CONF_CALCULATION_ENABLED_CONDITION not in self._sensor_config:
            return

        template: Template | str = self._sensor_config.get(CONF_CALCULATION_ENABLED_CONDITION)  # type: ignore
        if isinstance(template, str):
            template = Template(template, self.hass)

        self._calculation_enabled_condition = template

    async def _handle_source_entity_state_change(
        self,
        trigger_entity_id: str,
        state: State | None,
    ) -> None:
        """Update power sensor based on new dependent entity state."""
        self._standby_sensors.pop(self.entity_id, None)
        if self._sleep_power_timer:
            self._sleep_power_timer()
            self._sleep_power_timer = None

        discovery_by = self._power_profile.discovery_by if self._power_profile else DiscoveryBy.ENTITY
        if self.source_entity == DUMMY_ENTITY_ID and discovery_by == DiscoveryBy.ENTITY:
            state = State(self.source_entity, STATE_ON)

        if not state or not self._has_valid_state(state):
            _LOGGER.debug(
                "%s: Source entity has an invalid state, setting power sensor to unavailable",
                trigger_entity_id,
            )
            self._update_power_and_write_state(None)
            return

        await self._switch_sub_profile_dynamically(state)
        power = await self.calculate_power(state)

        _LOGGER.debug(
            '%s: State changed to "%s". Power:%s',
            state.entity_id,
            state.state,
            self._power,
        )

        self._update_power_and_write_state(power)
        async_dispatcher_send(self.hass, SIGNAL_POWER_SENSOR_STATE_CHANGE)

    def _update_power_and_write_state(self, power: Decimal | None) -> None:
        """Update the power sensor and write HA state."""

        available = False
        if power is not None:
            power = round(power, self._rounding_digits)
            available = True

        if self._availability_entity:
            state = self.hass.states.get(self._availability_entity)
            available = bool(state and state.state != STATE_UNAVAILABLE)

        # Prevent writing the same state twice to the state machine
        if self._power == power and self.available == available:
            return

        self._power = power
        self._attr_available = available
        self.async_write_ha_state()

    @callback
    def _update_power_sensor(self, power: Decimal) -> None:
        """Update the power sensor with new power value from strategy and write HA state."""
        if self._multiply_factor:
            power *= Decimal(self._multiply_factor)
        self._update_power_and_write_state(power)

    def _has_valid_state(self, state: State) -> bool:
        """Check if the state is valid, we can use it for power calculation."""
        if self.source_entity == DUMMY_ENTITY_ID:
            return True

        return self._ignore_unavailable_state or state.state not in [STATE_UNAVAILABLE, STATE_UNKNOWN]

    async def calculate_power(self, state: State) -> Decimal | None:
        """Calculate power consumption using configured strategy."""
        assert self._strategy_instance is not None

        # Resolve the relevant entity state
        entity_state = state
        if (
            self._calculation_strategy != CalculationStrategy.MULTI_SWITCH
            and self._source_entity.entity_id != DUMMY_ENTITY_ID
            and state.entity_id != self._source_entity.entity_id
            and (entity_state := self.hass.states.get(self._source_entity.entity_id)) is None
        ):
            return None

        # Handle unavailable power
        unavailable_power = self._sensor_config.get(CONF_UNAVAILABLE_POWER)
        if entity_state.state == STATE_UNAVAILABLE and unavailable_power is not None:
            return Decimal(unavailable_power)

        # Handle standby power
        standby_power = None
        if entity_state.state in self._off_states or not await self.is_calculation_enabled(entity_state):
            if isinstance(self._strategy_instance, PlaybookStrategy):
                await self._strategy_instance.stop_playbook()
            standby_power = await self.calculate_standby_power(entity_state)
            self._standby_sensors[self.entity_id] = standby_power

            if self._strategy_instance.can_calculate_standby() or self._calculation_strategy != CalculationStrategy.MULTI_SWITCH:
                return standby_power

        # Calculate actual power using configured strategy
        power = await self._strategy_instance.calculate(entity_state)
        if power is None:
            return None

        # Add standby power if available
        if standby_power:
            power += standby_power

        # Apply multiply factor to power
        if self._multiply_factor:
            power *= Decimal(self._multiply_factor)

        # Add standby power-on adjustments if applicable
        if self._standby_power_on and not standby_power:
            additional_standby_power = self._standby_power_on
            self._standby_sensors[self.entity_id] = self._standby_power_on
            if self._multiply_factor_standby and self._multiply_factor:
                additional_standby_power *= Decimal(self._multiply_factor)
            power += additional_standby_power

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
        """Selects a new sub profile on the power profile and updates standby power accordingly."""
        if not self._power_profile or self._power_profile.sub_profile == profile:
            return

        await self._power_profile.select_sub_profile(profile)
        self._standby_power = Decimal(self._power_profile.standby_power)
        self._standby_power_on = Decimal(self._power_profile.standby_power_on)
        await self.ensure_strategy_instance(True)

    async def calculate_standby_power(self, state: State) -> Decimal:
        """Calculate the power of the device in OFF state."""
        assert self._strategy_instance is not None
        sleep_power: dict[str, float] = self._sensor_config.get(CONF_SLEEP_POWER)  # type: ignore
        if sleep_power:
            delay = sleep_power.get(CONF_DELAY) or 0

            @callback
            def _update_sleep_power(*_: Any) -> None:  # noqa: ANN401
                power = Decimal(sleep_power.get(CONF_POWER) or 0)
                if self._multiply_factor_standby and self._multiply_factor:
                    power *= Decimal(self._multiply_factor)
                self._update_power_and_write_state(power)

            self._sleep_power_timer = async_call_later(
                self.hass,
                delay,
                _update_sleep_power,
            )

        standby_power = self._standby_power
        if self._strategy_instance.can_calculate_standby():
            standby_power = await self._strategy_instance.calculate(state) or self._standby_power

        evaluated = await evaluate_power(standby_power)
        if evaluated is None:
            evaluated = Decimal(0)
        standby_power = evaluated

        if self._multiply_factor_standby and self._multiply_factor:
            standby_power *= Decimal(self._multiply_factor)

        return standby_power

    async def is_calculation_enabled(self, entity_state: State) -> bool:
        """Check if calculation is enabled based on the condition template."""
        template = self._calculation_enabled_condition
        if not template:
            return self._strategy_instance.is_enabled(entity_state)  # type: ignore

        return bool(template.async_render())

    @property
    def source_entity(self) -> str:
        """The source entity this power sensor calculates power for."""
        return self._source_entity.entity_id

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return cast(StateType, self._power)

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
        """Get the active playbook"""
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

        known_profiles = [profile[0] for profile in await self._power_profile.get_sub_profiles()]
        if profile not in known_profiles:
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
