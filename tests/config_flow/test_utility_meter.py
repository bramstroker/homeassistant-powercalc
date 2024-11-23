from unittest.mock import patch

from homeassistant import data_entry_flow
from homeassistant.components.utility_meter.const import DAILY
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import (
    CONF_CREATE_UTILITY_METERS,
    CONF_MODE,
    CONF_POWER,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    CalculationStrategy,
)
from tests.config_flow.common import DEFAULT_ENTITY_ID, goto_virtual_power_strategy_step, set_virtual_power_configuration


async def test_utility_meter_tariffs(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        {
            CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    result = await set_virtual_power_configuration(hass, result, {CONF_POWER: 50})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_UTILITY_METER_TARIFFS: ["peak", "offpeak"],
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()

    tariff_select = hass.states.get("select.test_energy_daily")
    assert tariff_select
    assert tariff_select.state == "peak"

    assert hass.states.get("sensor.test_energy_daily_peak")
    assert hass.states.get("sensor.test_energy_daily_offpeak")


async def test_utility_meter_net_consumption(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        {
            CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    result = await set_virtual_power_configuration(hass, result, {CONF_POWER: 50})

    with patch("custom_components.powercalc.sensors.utility_meter.VirtualUtilityMeter") as mock_utility_meter:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_UTILITY_METER_TYPES: [DAILY],
                CONF_UTILITY_METER_NET_CONSUMPTION: True,
            },
        )

        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

        _, kwargs = mock_utility_meter.call_args
        assert kwargs["net_consumption"] is True
