from datetime import timedelta
from decimal import Decimal

import homeassistant.util.dt as dt_util
import pytest
from freezegun import freeze_time
from homeassistant.components.utility_meter.sensor import SensorDeviceClass
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import (
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import CONF_MIN_TIME, CONF_POWER_THRESHOLD, CONF_UNTRACKED_ENERGY
from tests.common import (
    run_powercalc_setup,
)


@pytest.mark.parametrize(
    "states",
    [
        [
            (Decimal(250), 0, Decimal(0)),
            (Decimal(280), 30, Decimal(0)),
            (Decimal(250), 60, Decimal(0)),
            (Decimal(420), 90, Decimal(0)),
            (Decimal(300), 150, Decimal(0.0135)),
        ],
        [
            (Decimal(1000), 0, Decimal(0)),
            (Decimal(1000), 3600, Decimal(1.0)),  # todo, implement sub interval when power is constant
        ],
        [
            (Decimal(250), 0, Decimal(0)),
            (Decimal(120), 60, Decimal(0)),  # lower value seen
            (Decimal(300), 150, Decimal(0)),
        ],
    ],
)
async def test_untracked_energy_sensor(
    hass: HomeAssistant,
    states: list[tuple[Decimal, int, Decimal]],
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
            CONF_UNTRACKED_ENERGY: {
                CONF_POWER_THRESHOLD: 200,
                CONF_MIN_TIME: timedelta(minutes=2),
            },
        },
    )

    await hass.async_block_till_done()

    for state, seconds, expected in states:
        with freeze_time(dt_util.utcnow() + timedelta(seconds=seconds)):
            hass.states.async_set("sensor.mains_power", state)
            await hass.async_block_till_done()
            energy = Decimal(hass.states.get("sensor.untracked_energy").state)
            assert round(energy, 4) == round(expected, 4)
