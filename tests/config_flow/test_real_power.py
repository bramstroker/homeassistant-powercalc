from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_CREATE_UTILITY_METERS, SensorType
from tests.config_flow.common import select_sensor_type


async def test_real_power(hass: HomeAssistant) -> None:
    result = await select_sensor_type(hass, SensorType.REAL_POWER)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Washing machine",
            CONF_ENTITY_ID: "sensor.washing_machine_power",
            CONF_CREATE_UTILITY_METERS: True,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()
    assert hass.states.get("sensor.washing_machine_energy")
    assert hass.states.get("sensor.washing_machine_energy_daily")


async def test_real_power_options(hass: HomeAssistant) -> None:
    pass
