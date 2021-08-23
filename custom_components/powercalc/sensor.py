"""Platform for sensor integration."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import homeassistant.helpers.config_validation as cv
import homeassistant.helpers.entity_registry as er
import voluptuous as vol
from homeassistant.components import (
    binary_sensor,
    climate,
    fan,
    input_boolean,
    light,
    media_player,
    remote,
    sensor,
    switch,
)
from homeassistant.components.hue.const import DOMAIN as HUE_DOMAIN
from homeassistant.components.integration.sensor import (
    TRAPEZOIDAL_METHOD,
    IntegrationSensor,
)
from homeassistant.components.light import PLATFORM_SCHEMA, Light
from homeassistant.components.sensor import STATE_CLASS_MEASUREMENT
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEVICE_CLASS_POWER,
    EVENT_HOMEASSISTANT_START,
    POWER_WATT,
    STATE_OFF,
    STATE_STANDBY,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    TIME_HOURS,
)
from homeassistant.core import callback, split_entity_id
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

from .const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_DISABLE_STANDBY_USAGE,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_FIXED,
    CONF_LINEAR,
    CONF_MANUFACTURER,
    CONF_MAX_WATT,
    CONF_MIN_WATT,
    CONF_MODE,
    CONF_MODEL,
    CONF_MULTIPLY_FACTOR,
    CONF_POWER_SENSOR_NAMING,
    CONF_STANDBY_USAGE,
    CONF_WATT,
    DATA_CALCULATOR_FACTORY,
    DOMAIN,
    DOMAIN_CONFIG,
    MODE_FIXED,
    MODE_LINEAR,
    MODE_LUT,
)
from .errors import ModelNotSupported, StrategyConfigurationError, UnsupportedMode
from .light_model import LightModel
from .strategy_fixed import CONFIG_SCHEMA as FIXED_SCHEMA
from .strategy_interface import PowerCalculationStrategyInterface
from .strategy_linear import CONFIG_SCHEMA as LINEAR_SCHEMA

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.All(
    cv.deprecated(CONF_MIN_WATT),
    cv.deprecated(CONF_MAX_WATT),
    cv.deprecated(CONF_WATT),
    PLATFORM_SCHEMA.extend(
        {
            vol.Optional(CONF_NAME): cv.string,
            vol.Required(CONF_ENTITY_ID): cv.entity_domain(
                (
                    light.DOMAIN,
                    switch.DOMAIN,
                    fan.DOMAIN,
                    binary_sensor.DOMAIN,
                    climate.DOMAIN,
                    remote.DOMAIN,
                    media_player.DOMAIN,
                    input_boolean.DOMAIN,
                    sensor.DOMAIN,
                )
            ),
            vol.Optional(CONF_MODEL): cv.string,
            vol.Optional(CONF_MANUFACTURER): cv.string,
            vol.Optional(CONF_MODE): vol.In([MODE_LUT, MODE_FIXED, MODE_LINEAR]),
            vol.Optional(CONF_MIN_WATT): cv.string,
            vol.Optional(CONF_MAX_WATT): cv.string,
            vol.Optional(CONF_WATT): cv.string,
            vol.Optional(CONF_STANDBY_USAGE): vol.Coerce(float),
            vol.Optional(CONF_DISABLE_STANDBY_USAGE, default=False): cv.boolean,
            vol.Optional(CONF_CUSTOM_MODEL_DIRECTORY): cv.string,
            vol.Optional(CONF_FIXED): FIXED_SCHEMA,
            vol.Optional(CONF_LINEAR): LINEAR_SCHEMA,
            vol.Optional(CONF_CREATE_ENERGY_SENSOR): cv.boolean,
            vol.Optional(CONF_MULTIPLY_FACTOR): vol.Coerce(float),
        }
    ),
)

ENERGY_ICON = "mdi:lightning-bolt"
ATTR_SOURCE_ENTITY = "source_entity"
ATTR_SOURCE_DOMAIN = "source_domain"


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
):
    """Set up the sensor platform."""

    calculation_strategy_factory = hass.data[DOMAIN][DATA_CALCULATOR_FACTORY]
    component_config = hass.data[DOMAIN][DOMAIN_CONFIG]

    source_entity = config[CONF_ENTITY_ID]

    entity_registry = await er.async_get_registry(hass)
    entity_entry = entity_registry.async_get(source_entity)
    entity_state = hass.states.get(source_entity)

    unique_id = None

    if entity_entry:
        entity_name = entity_entry.name or entity_entry.original_name
        source_entity_domain = entity_entry.domain
        unique_id = entity_entry.unique_id
    elif entity_state:
        entity_name = entity_state.name
        source_entity_domain = entity_state.domain
    else:
        entity_name = split_entity_id(source_entity)[1].replace("_", " ")
        source_entity_domain = split_entity_id(source_entity)[0]

    light_model = None
    try:
        light_model = await get_light_model(hass, entity_entry, config)
    except (ModelNotSupported) as err:
        _LOGGER.info("Model not found in library %s: %s", source_entity, err)

    try:
        mode = select_calculation_mode(config, light_model)
        calculation_strategy = calculation_strategy_factory.create(
            config, mode, light_model, source_entity_domain
        )
        await calculation_strategy.validate_config(entity_entry)
    except (ModelNotSupported, UnsupportedMode) as err:
        _LOGGER.error("Skipping sensor setup %s: %s", source_entity, err)
        return
    except StrategyConfigurationError as err:
        _LOGGER.error("Error setting up calculation strategy: %s", err)
        return

    standby_usage = None
    if not config.get(CONF_DISABLE_STANDBY_USAGE):
        standby_usage = config.get(CONF_STANDBY_USAGE)
        if standby_usage is None and light_model is not None:
            standby_usage = light_model.standby_usage

    power_name_pattern = component_config.get(CONF_POWER_SENSOR_NAMING)
    name = config.get(CONF_NAME) or power_name_pattern.format(entity_name)

    _LOGGER.debug(
        "Setting up power sensor. entity_id:%s sensor_name:%s strategy=%s manufacturer=%s model=%s standby_usage=%s",
        source_entity,
        name,
        calculation_strategy.__class__.__name__,
        light_model.manufacturer if light_model else "",
        light_model.model if light_model else "",
        standby_usage,
    )

    power_sensor = VirtualPowerSensor(
        hass=hass,
        power_calculator=calculation_strategy,
        name=name,
        source_entity=source_entity,
        source_domain=source_entity_domain,
        unique_id=unique_id,
        standby_usage=standby_usage,
        scan_interval=component_config.get(CONF_SCAN_INTERVAL),
        multiply_factor=config.get(CONF_MULTIPLY_FACTOR),
    )

    entities_to_add = [power_sensor]

    should_create_energy_sensor = component_config.get(CONF_CREATE_ENERGY_SENSORS)
    if CONF_CREATE_ENERGY_SENSOR in config:
        should_create_energy_sensor = config.get(CONF_CREATE_ENERGY_SENSOR)

    if should_create_energy_sensor:
        energy_name_pattern = component_config.get(CONF_ENERGY_SENSOR_NAMING)
        energy_sensor_name = energy_name_pattern.format(entity_name)

        _LOGGER.debug("Creating energy sensor: %s", energy_sensor_name)
        entities_to_add.append(
            VirtualEnergySensor(
                source_entity=power_sensor.entity_id,
                name=energy_sensor_name,
                round_digits=4,
                unit_prefix="k",
                unit_of_measurement=None,
                unit_time=TIME_HOURS,
                integration_method=TRAPEZOIDAL_METHOD,
                powercalc_source_entity=source_entity,
                powercalc_source_domain=source_entity_domain,
            )
        )

    async_add_entities(entities_to_add)


def select_calculation_mode(config: dict, light_model: LightModel):
    """Select the calculation mode"""
    config_mode = config.get(CONF_MODE)
    if config_mode:
        return config_mode

    if config.get(CONF_LINEAR):
        return MODE_LINEAR

    if config.get(CONF_FIXED):
        return MODE_FIXED

    if light_model:
        return light_model.supported_modes[0]

    # BC compat, can be removed in v0.5
    if config.get(CONF_MIN_WATT):
        return MODE_LINEAR

    # BC compat, can be removed in v0.5
    if config.get(CONF_WATT):
        return MODE_FIXED

    raise UnsupportedMode(
        "Cannot select a mode (LINEAR, FIXED or LUT), supply it in the config"
    )


async def get_light_model(
    hass: HomeAssistantType, entity_entry, config: dict
) -> Optional[LightModel]:
    manufacturer = config.get(CONF_MANUFACTURER)
    model = config.get(CONF_MODEL)
    if (manufacturer is None or model is None) and entity_entry:
        hue_model_data = await autodiscover_hue_model(hass, entity_entry)
        if hue_model_data:
            manufacturer = hue_model_data["manufacturer"]
            model = hue_model_data["model"]

    if manufacturer is None or model is None:
        return None

    custom_model_directory = config.get(CONF_CUSTOM_MODEL_DIRECTORY)
    if custom_model_directory:
        custom_model_directory = os.path.join(
            hass.config.config_dir, custom_model_directory
        )

    return LightModel(manufacturer, model, custom_model_directory)


async def autodiscover_hue_model(hass: HomeAssistantType, entity_entry):
    # When Philips Hue model is enabled we can auto discover manufacturer and model from the bridge data
    if hass.data.get(HUE_DOMAIN) is None or entity_entry.platform != "hue":
        return

    light = await find_hue_light(hass, entity_entry)
    if light is None:
        _LOGGER.error(
            "Cannot autodiscover model for '%s', not found in the hue bridge api",
            entity_entry.entity_id,
        )
        return

    _LOGGER.debug(
        "Auto discovered Hue model for entity %s: (manufacturer=%s, model=%s)",
        entity_entry.entity_id,
        light.manufacturername,
        light.modelid,
    )

    return {"manufacturer": light.manufacturername, "model": light.modelid}


async def find_hue_light(
    hass: HomeAssistantType, entity_entry: er.RegistryEntry
) -> Light | None:
    """Find the light in the Hue bridge, we need to extract the model id."""

    bridge = hass.data[HUE_DOMAIN][entity_entry.config_entry_id]
    lights = bridge.api.lights
    for light_id in lights:
        light = bridge.api.lights[light_id]
        if light.uniqueid == entity_entry.unique_id:
            return light

    return None


class VirtualPowerSensor(Entity):
    """Representation of a Sensor."""

    _attr_device_class = DEVICE_CLASS_POWER
    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_unit_of_measurement = POWER_WATT

    def __init__(
        self,
        hass: HomeAssistantType,
        power_calculator: PowerCalculationStrategyInterface,
        name: str,
        source_entity: str,
        source_domain: str,
        unique_id: str,
        standby_usage: float | None,
        scan_interval,
        multiply_factor: float | None,
    ):
        """Initialize the sensor."""
        self._power_calculator = power_calculator
        self._source_entity = source_entity
        self._source_domain = source_domain
        self._name = name
        self._power = None
        self._unique_id = unique_id
        self._standby_usage = standby_usage
        self._attr_force_update = True
        self._scan_interval = scan_interval
        self._multiply_factor = multiply_factor
        self.entity_id = async_generate_entity_id("sensor.{}", name, hass=hass)

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

        if state.state == STATE_OFF or state.state == STATE_STANDBY:
            self._power = self._standby_usage or 0
        else:
            self._power = await self._power_calculator.calculate(state)
            if self._multiply_factor:
                self._power *= self._multiply_factor

        if self._power is None:
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
    def unique_id(self):
        """Return a unique id."""
        return self._unique_id

    @property
    def available(self):
        """Return True if entity is available."""
        return self._power is not None


class VirtualEnergySensor(IntegrationSensor):
    def __init__(
        self,
        source_entity,
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
