from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITY_ID, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_CREATE_UTILITY_METERS, CONF_MODE, CONF_POWER, CONF_UTILITY_METER_TARIFFS, CalculationStrategy
from tests.config_flow.common import DEFAULT_ENTITY_ID, DEFAULT_UNIQUE_ID, goto_virtual_power_strategy_step


async def test_utility_meter_tariffs(hass: HomeAssistant) -> None:
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.FIXED,
        {
            CONF_ENTITY_ID: DEFAULT_ENTITY_ID,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_POWER: 50},
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert CONF_UTILITY_METER_TARIFFS in result["data_schema"].schema

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_UTILITY_METER_TARIFFS: ["peak", "offpeak"]},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()

    tariff_select = hass.states.get("select.test_energy_daily")
    assert tariff_select
    assert tariff_select.state == "peak"

    assert hass.states.get("sensor.test_energy_daily_peak")
    assert hass.states.get("sensor.test_energy_daily_offpeak")
