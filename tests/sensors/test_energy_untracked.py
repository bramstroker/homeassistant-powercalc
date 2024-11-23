import logging
import homeassistant.util.dt as dt_util
from datetime import timedelta
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.components.utility_meter.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.util import dt
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_GROUP,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_SENSOR_ID,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_FIXED,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    DOMAIN,
    SERVICE_CALIBRATE_ENERGY,
    UnitPrefix,
)
from custom_components.powercalc.sensors.energy import VirtualEnergySensor
from tests.common import (
    create_input_boolean,
    get_simple_fixed_config,
    run_powercalc_setup,
)


async def test_untracked_energy_sensor(
    hass: HomeAssistant,
) -> None:
    mock_device_registry(
        hass,
        {
            "some-device": DeviceEntry(
                id="some-device",
                manufacturer="Shelly",
                model="Shelly EM",
            ),
        },
    )

    mock_registry(
        hass,
        {
            "sensor.mains_power": RegistryEntry(
                entity_id="sensor.mains_power",
                unique_id="1234",
                platform="sensor",
                device_id="some-device",
                device_class=SensorDeviceClass.POWER,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "sensor.mains_power",
            CONF_NAME: "untracked",
            "untracked": {
                "power_exceeds": 200,
                "min_time": timedelta(minutes=2),
            }
        },
    )

    await hass.async_block_till_done()

    hass.states.async_set("sensor.mains_power", 250)
    await hass.async_block_till_done()

    with freeze_time(dt_util.utcnow() + timedelta(seconds=30)):
        hass.states.async_set("sensor.mains_power", 280)
        await hass.async_block_till_done()

    with freeze_time(dt_util.utcnow() + timedelta(seconds=60)):
        hass.states.async_set("sensor.mains_power", 250)
        await hass.async_block_till_done()

    with freeze_time(dt_util.utcnow() + timedelta(seconds=90)):
        hass.states.async_set("sensor.mains_power", 420)
        await hass.async_block_till_done()

    with freeze_time(dt_util.utcnow() + timedelta(seconds=150)):
        hass.states.async_set("sensor.mains_power", 300)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.untracked_energy")
    assert state
    assert state.state == "0.0064"
