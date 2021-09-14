"""Platform for sensor integration."""

from __future__ import annotations

import logging
from typing import Any, Optional

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from homeassistant.components import (
    binary_sensor,
    climate,
    device_tracker,
    fan,
    input_boolean,
    input_select,
    light,
    media_player,
    remote,
    sensor,
    switch,
    vacuum,
    water_heater,
)
from homeassistant.components.integration.sensor import (
    TRAPEZOIDAL_METHOD,
    IntegrationSensor,
)
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.components.utility_meter import DEFAULT_OFFSET
from homeassistant.components.utility_meter.const import METER_TYPES
from homeassistant.components.utility_meter.sensor import UtilityMeterSensor
from homeassistant.const import (
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER,
    ENERGY_KILO_WATT_HOUR,
    EVENT_HOMEASSISTANT_START,
    POWER_WATT,
    STATE_NOT_HOME,
    STATE_OFF,
    STATE_STANDBY,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    TIME_HOURS,
)
from homeassistant.core import State, callback, split_entity_id
from homeassistant.helpers.entity import Entity, async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

from .common import SourceEntity, validate_name_pattern
from .const import (
    CALCULATION_MODES,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_GROUP,
    CONF_CREATE_UTILITY_METERS,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_DISABLE_STANDBY_USAGE,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_MULTIPLY_FACTOR_STANDBY,
    CONF_POWER_SENSOR_NAMING,
    CONF_STANDBY_USAGE,
    CONF_UTILITY_METER_TYPES,
    DATA_CALCULATOR_FACTORY,
    DOMAIN,
    DOMAIN_CONFIG,
    MODE_FIXED,
    MODE_LINEAR,
)
from .errors import (
    ModelNotSupported,
    PowercalcSetupError,
    SensorConfigurationError,
    StrategyConfigurationError,
    UnsupportedMode,
)
from .model_discovery import get_light_model
from .strategy_fixed import CONFIG_SCHEMA as FIXED_SCHEMA
from .strategy_interface import PowerCalculationStrategyInterface
from .strategy_linear import CONFIG_SCHEMA as LINEAR_SCHEMA

_LOGGER = logging.getLogger(__name__)

SUPPORTED_ENTITY_DOMAINS = (
    light.DOMAIN,
    switch.DOMAIN,
    fan.DOMAIN,
    binary_sensor.DOMAIN,
    climate.DOMAIN,
    device_tracker.DOMAIN,
    remote.DOMAIN,
    media_player.DOMAIN,
    input_boolean.DOMAIN,
    input_select.DOMAIN,
    sensor.DOMAIN,
    vacuum.DOMAIN,
    water_heater.DOMAIN,
)

SENSOR_CONFIG = {
    vol.Optional(CONF_NAME): cv.string,
    vol.Optional(CONF_ENTITY_ID): cv.entity_domain(SUPPORTED_ENTITY_DOMAINS),
    vol.Optional(CONF_MODEL): cv.string,
    vol.Optional(CONF_MANUFACTURER): cv.string,
    vol.Optional(CONF_MODE): vol.In(CALCULATION_MODES),
    vol.Optional(CONF_STANDBY_USAGE): vol.Coerce(float),
    vol.Optional(CONF_DISABLE_STANDBY_USAGE, default=False): cv.boolean,
    vol.Optional(CONF_CUSTOM_MODEL_DIRECTORY): cv.string,
    vol.Optional(CONF_FIXED): FIXED_SCHEMA,
    vol.Optional(CONF_LINEAR): LINEAR_SCHEMA,
    vol.Optional(CONF_CREATE_ENERGY_SENSOR): cv.boolean,
    vol.Optional(CONF_CREATE_UTILITY_METERS): cv.boolean,
    vol.Optional(CONF_UTILITY_METER_TYPES): vol.All(
        cv.ensure_list, [vol.In(METER_TYPES)]
    ),
    vol.Optional(CONF_MULTIPLY_FACTOR): vol.Coerce(float),
    vol.Optional(CONF_MULTIPLY_FACTOR_STANDBY, default=False): cv.boolean,
    vol.Optional(CONF_POWER_SENSOR_NAMING): validate_name_pattern,
    vol.Optional(CONF_ENERGY_SENSOR_NAMING): validate_name_pattern,
}

PLATFORM_SCHEMA = vol.All(
    PLATFORM_SCHEMA.extend(
        {
            **SENSOR_CONFIG,
            **{
                vol.Optional(CONF_CREATE_GROUP): cv.string,
                vol.Optional(CONF_ENTITIES, None): vol.All(
                    cv.ensure_list, [SENSOR_CONFIG]
                ),
            },
        }
    ),
)

ENERGY_ICON = "mdi:lightning-bolt"
ATTR_CALCULATION_MODE = "calculation_mode"
ATTR_INTEGRATION = "integration"
ATTR_SOURCE_ENTITY = "source_entity"
ATTR_SOURCE_DOMAIN = "source_domain"
OFF_STATES = [STATE_OFF, STATE_NOT_HOME, STATE_STANDBY]


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
):
    """Set up the sensor platform."""

    global_config = hass.data[DOMAIN][DOMAIN_CONFIG]

    entities = []
    try:
        if CONF_ENTITIES in config:
            for sensor_config in config.get(CONF_ENTITIES):
                merged_sensor_config = get_sensor_configuration(
                    sensor_config, global_config
                )
                entities.extend(
                    await create_individual_sensors(hass, merged_sensor_config)
                )

            if CONF_CREATE_GROUP in config:
                group_name = config.get(CONF_CREATE_GROUP)
                group_sensors = create_group_sensors(
                    group_name, merged_sensor_config, entities
                )
                entities.extend(group_sensors)
        else:
            merged_sensor_config = get_sensor_configuration(config, global_config)
            entities.extend(await create_individual_sensors(hass, merged_sensor_config))
    except SensorConfigurationError as err:
        _LOGGER.error(err)
        return

    if entities:
        async_add_entities(entities)


async def create_individual_sensors(
    hass: HomeAssistantType, sensor_config: dict
) -> list[SensorEntity]:
    """Create entities (power, energy, utility_meters) which track the appliance."""

    source_entity = sensor_config[CONF_ENTITY_ID]
    source_entity_domain, source_object_id = split_entity_id(source_entity)

    entity_registry = await er.async_get_registry(hass)
    entity_entry = entity_registry.async_get(source_entity)

    unique_id = None
    if entity_entry:
        source_entity_name = entity_entry.name or entity_entry.original_name
        source_entity_domain = entity_entry.domain
        unique_id = entity_entry.unique_id
    else:
        source_entity_name = source_object_id.replace("_", " ")

    entity_state = hass.states.get(source_entity)
    if entity_state:
        source_entity_name = entity_state.name

    capabilities = entity_entry.capabilities if entity_entry else []
    source_entity = SourceEntity(
        unique_id,
        source_object_id,
        source_entity,
        source_entity_name,
        source_entity_domain,
        capabilities,
    )

    try:
        power_sensor = await create_power_sensor(
            hass, entity_entry, sensor_config, source_entity
        )
    except PowercalcSetupError as err:
        return []

    entities_to_add = [power_sensor]

    if sensor_config.get(CONF_CREATE_ENERGY_SENSOR):
        energy_sensor = await create_energy_sensor(
            hass, sensor_config, power_sensor, source_entity
        )
        entities_to_add.append(energy_sensor)

        if sensor_config.get(CONF_CREATE_UTILITY_METERS):
            meter_types = sensor_config.get(CONF_UTILITY_METER_TYPES)
            for meter_type in meter_types:
                entities_to_add.append(
                    create_utility_meter_sensor(energy_sensor, meter_type)
                )

    return entities_to_add


def create_group_sensors(
    group_name: str, sensor_config: dict, entities: list[SensorEntity]
) -> list[GroupedSensor]:
    """Create grouped power and energy sensors."""

    group_sensors = []

    power_sensors = list(
        filter(lambda elm: isinstance(elm, VirtualPowerSensor), entities)
    )
    power_sensor_ids = list(map(lambda x: x.entity_id, power_sensors))
    name_pattern = sensor_config.get(CONF_POWER_SENSOR_NAMING)
    name = name_pattern.format(group_name)
    group_sensors.append(GroupedPowerSensor(name, power_sensor_ids))
    _LOGGER.debug("Creating grouped power sensor: %s", name)

    energy_sensors = list(
        filter(lambda elm: isinstance(elm, VirtualEnergySensor), entities)
    )
    energy_sensor_ids = list(map(lambda x: x.entity_id, energy_sensors))
    name_pattern = sensor_config.get(CONF_ENERGY_SENSOR_NAMING)
    name = name_pattern.format(group_name)
    group_sensors.append(GroupedEnergySensor(name, energy_sensor_ids))
    _LOGGER.debug("Creating grouped energy sensor: %s", name)

    return group_sensors


def get_sensor_configuration(config: dict, global_config: dict) -> dict:
    """Build the configuration dictionary for the sensors."""

    if not CONF_ENTITY_ID in config:
        raise SensorConfigurationError(
            "You must supply a entity_id in the configuration, see the README"
        )

    fallbackAttributes = (
        CONF_CREATE_UTILITY_METERS,
        CONF_ENERGY_SENSOR_NAMING,
        CONF_POWER_SENSOR_NAMING,
        CONF_UTILITY_METER_TYPES,
    )

    # When not set on sensor level will fallback to global level configuration
    for attribute in fallbackAttributes:
        if not attribute in config:
            config[attribute] = global_config.get(attribute)

    if not CONF_CREATE_ENERGY_SENSOR in config:
        config[CONF_CREATE_ENERGY_SENSOR] = global_config.get(
            CONF_CREATE_ENERGY_SENSORS
        )

    config[CONF_SCAN_INTERVAL] = global_config.get(CONF_SCAN_INTERVAL)

    return config


async def create_power_sensor(
    hass: HomeAssistantType,
    entity_entry,
    sensor_config: dict,
    source_entity: SourceEntity,
) -> VirtualPowerSensor:
    """Create the power sensor entity"""
    calculation_strategy_factory = hass.data[DOMAIN][DATA_CALCULATOR_FACTORY]

    name_pattern = sensor_config.get(CONF_POWER_SENSOR_NAMING)
    name = sensor_config.get(CONF_NAME) or source_entity.name
    name = name_pattern.format(name)
    object_id = sensor_config.get(CONF_NAME) or source_entity.object_id
    entity_id = async_generate_entity_id(
        "sensor.{}", name_pattern.format(object_id), hass=hass
    )

    light_model = None
    try:
        mode = select_calculation_mode(sensor_config)
        if (
            sensor_config.get(CONF_LINEAR) is None
            and sensor_config.get(CONF_FIXED) is None
        ):
            light_model = await get_light_model(hass, entity_entry, sensor_config)
            if mode is None and light_model:
                mode = light_model.supported_modes[0]

        if mode is None:
            raise UnsupportedMode(
                "Cannot select a mode (LINEAR, FIXED or LUT), supply it in the config"
            )

        calculation_strategy = calculation_strategy_factory.create(
            sensor_config, mode, light_model, source_entity.domain
        )
        await calculation_strategy.validate_config(source_entity)
    except (ModelNotSupported, UnsupportedMode) as err:
        _LOGGER.error("Skipping sensor setup %s: %s", source_entity.entity_id, err)
        raise err
    except StrategyConfigurationError as err:
        _LOGGER.error(
            "Error setting up calculation strategy for %s: %s",
            source_entity.entity_id,
            err,
        )
        raise err

    standby_usage = None
    if not sensor_config.get(CONF_DISABLE_STANDBY_USAGE):
        standby_usage = sensor_config.get(CONF_STANDBY_USAGE)
        if standby_usage is None and light_model is not None:
            standby_usage = light_model.standby_usage

    _LOGGER.debug(
        "Creating power sensor (entity_id=%s sensor_name=%s strategy=%s manufacturer=%s model=%s standby_usage=%s unique_id=%s)",
        source_entity.entity_id,
        name,
        calculation_strategy.__class__.__name__,
        light_model.manufacturer if light_model else "",
        light_model.model if light_model else "",
        standby_usage,
        source_entity.unique_id,
    )

    return VirtualPowerSensor(
        power_calculator=calculation_strategy,
        calculation_mode=mode,
        entity_id=entity_id,
        name=name,
        source_entity=source_entity.entity_id,
        source_domain=source_entity.domain,
        unique_id=source_entity.unique_id,
        standby_usage=standby_usage,
        scan_interval=sensor_config.get(CONF_SCAN_INTERVAL),
        multiply_factor=sensor_config.get(CONF_MULTIPLY_FACTOR),
        multiply_factor_standby=sensor_config.get(CONF_MULTIPLY_FACTOR_STANDBY),
    )


async def create_energy_sensor(
    hass: HomeAssistantType,
    sensor_config: dict,
    power_sensor: VirtualPowerSensor,
    source_entity: SourceEntity,
) -> VirtualEnergySensor:
    """Create the energy sensor entity"""

    name_pattern = sensor_config.get(CONF_ENERGY_SENSOR_NAMING)
    name = sensor_config.get(CONF_NAME) or source_entity.name
    name = name_pattern.format(name)
    object_id = sensor_config.get(CONF_NAME) or source_entity.object_id
    entity_id = async_generate_entity_id(
        "sensor.{}", name_pattern.format(object_id), hass=hass
    )

    _LOGGER.debug("Creating energy sensor: %s", name)
    return VirtualEnergySensor(
        source_entity=power_sensor.entity_id,
        unique_id=source_entity.unique_id,
        entity_id=entity_id,
        name=name,
        round_digits=4,
        unit_prefix="k",
        unit_of_measurement=None,
        unit_time=TIME_HOURS,
        integration_method=TRAPEZOIDAL_METHOD,
        powercalc_source_entity=source_entity.entity_id,
        powercalc_source_domain=source_entity.domain,
    )


def create_utility_meter_sensor(
    energy_sensor: VirtualEnergySensor, meter_type: str
) -> VirtualUtilityMeterSensor:
    """Create the utility meter sensor entity"""
    name = f"{energy_sensor.name} {meter_type}"
    entity_id = f"{energy_sensor.entity_id}_{meter_type}"
    _LOGGER.debug("Creating utility_meter sensor: %s", name)
    return VirtualUtilityMeterSensor(
        energy_sensor.entity_id, name, meter_type, entity_id
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

    return None


class VirtualPowerSensor(Entity):
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
        standby_usage: float | None,
        scan_interval,
        multiply_factor: float | None,
        multiply_factor_standby: bool,
    ):
        """Initialize the sensor."""
        self._power_calculator = power_calculator
        self._calculation_mode = calculation_mode
        self._source_entity = source_entity
        self._source_domain = source_domain
        self._name = name
        self._power = None
        self._standby_usage = standby_usage
        self._attr_force_update = True
        self._attr_unique_id = unique_id
        self._scan_interval = scan_interval
        self._multiply_factor = multiply_factor
        self._multiply_factor_standby = multiply_factor_standby
        self.entity_id = entity_id

    async def async_added_to_hass(self):
        """Register callbacks."""

        async def appliance_state_listener(event):
            """Handle for state changes for dependent sensors."""
            new_state = event.data.get("new_state")

            await self._update_power_sensor(new_state)

        async def home_assistant_startup(event):
            """Add listeners and get initial state."""

            async_track_state_change_event(
                self.hass, [self._source_entity], appliance_state_listener
            )

            new_state = self.hass.states.get(self._source_entity)

            await self._update_power_sensor(new_state)

        @callback
        def async_update(event_time=None):
            """Update the entity."""
            self.async_schedule_update_ha_state(True)

        async_track_time_interval(self.hass, async_update, self._scan_interval)

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_START, home_assistant_startup
        )

    async def _update_power_sensor(self, state) -> bool:
        """Update power sensor based on new dependant hue light state."""
        if (
            state is None
            or state.state == STATE_UNKNOWN
            or state.state == STATE_UNAVAILABLE
        ):
            self._power = None
            self.async_write_ha_state()
            return False

        if state.state in OFF_STATES:
            self._power = self._standby_usage or 0
            if self._multiply_factor and self._multiply_factor_standby:
                self._power *= self._multiply_factor
        else:
            self._power = await self._power_calculator.calculate(state)
            if self._multiply_factor and self._power is not None:
                self._power *= self._multiply_factor

        if self._power is None:
            self.async_write_ha_state()
            return False

        self._power = round(self._power, 2)

        _LOGGER.debug(
            'State changed to "%s" for entity "%s". Power:%s',
            state.state,
            state.entity_id,
            self._power,
        )

        self.async_write_ha_state()
        return True

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


class VirtualEnergySensor(IntegrationSensor):
    """Virtual energy sensor, totalling kWh"""

    def __init__(
        self,
        source_entity,
        unique_id,
        entity_id,
        name,
        round_digits,
        unit_prefix,
        unit_time,
        unit_of_measurement,
        integration_method,
        powercalc_source_entity: str,
        powercalc_source_domain: str,
    ):
        super().__init__(
            source_entity,
            name,
            round_digits,
            unit_prefix,
            unit_time,
            unit_of_measurement,
            integration_method,
        )
        self._powercalc_source_entity = powercalc_source_entity
        self._powercalc_source_domain = powercalc_source_domain
        self.entity_id = entity_id
        if unique_id:
            self._attr_unique_id = f"{unique_id}_energy"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes of the acceleration sensor."""
        state_attr = super().extra_state_attributes
        state_attr[ATTR_SOURCE_ENTITY] = self._powercalc_source_entity
        state_attr[ATTR_SOURCE_DOMAIN] = self._powercalc_source_domain
        return state_attr

    @property
    def icon(self):
        return ENERGY_ICON


class VirtualUtilityMeterSensor(UtilityMeterSensor):
    """Utility meter resets on each cycle (daily, hourly etc)"""

    def __init__(self, source_entity, name, meter_type, entity_id):
        super().__init__(source_entity, name, meter_type, DEFAULT_OFFSET, False)
        self.entity_id = entity_id


class GroupedSensor(SensorEntity):
    """Base class for grouped sensors"""

    _attr_should_poll = False

    def __init__(self, name: str, entities: list[str]):
        self._attr_name = name
        self._entities = entities

    async def async_added_to_hass(self) -> None:
        """Register state listeners."""
        async_track_state_change_event(self.hass, self._entities, self.on_state_change)

    @callback
    def on_state_change(self, event):
        """Triggered when one of the group entities changes state"""
        all_states = [self.hass.states.get(entity_id) for entity_id in self._entities]
        states: list[State] = list(filter(None, all_states))
        summed = sum(
            float(state.state) for state in states if state.state != STATE_UNAVAILABLE
        )
        self._attr_native_value = round(summed, 2)
        self.async_schedule_update_ha_state(True)


class GroupedPowerSensor(GroupedSensor):
    """Grouped power sensor. Sums all values of underlying individual power sensors"""

    _attr_device_class = DEVICE_CLASS_POWER
    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_unit_of_measurement = POWER_WATT


class GroupedEnergySensor(GroupedSensor):
    """Grouped energy sensor. Sums all values of underlying individual energy sensors"""

    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_unit_of_measurement = ENERGY_KILO_WATT_HOUR
