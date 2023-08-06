from homeassistant import data_entry_flow
from homeassistant.const import CONF_NAME, CONF_UNIQUE_ID, CONF_UNIT_OF_MEASUREMENT, UnitOfPower
from homeassistant.core import HomeAssistant

from custom_components.powercalc import SensorType
from custom_components.powercalc.const import CONF_DAILY_FIXED_ENERGY, CONF_SENSOR_TYPE, CONF_UPDATE_FREQUENCY, CONF_VALUE
from tests.config_flow.common import DEFAULT_UNIQUE_ID, create_mock_entry, initialize_options_flow, select_sensor_type


async def test_daily_energy_mandatory_fields_not_supplied(hass: HomeAssistant) -> None:
    result = await select_sensor_type(hass, SensorType.DAILY_ENERGY)

    user_input = {CONF_NAME: "My daily energy sensor"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]
    assert result["errors"] == {"base": "daily_energy_mandatory"}


async def test_create_daily_energy_entry(hass: HomeAssistant) -> None:
    result = await select_sensor_type(hass, SensorType.DAILY_ENERGY)

    user_input = {
        CONF_NAME: "My daily energy sensor",
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        CONF_VALUE: 0.5,
        CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
        CONF_NAME: "My daily energy sensor",
        CONF_DAILY_FIXED_ENERGY: {
            CONF_UPDATE_FREQUENCY: 1800,
            CONF_VALUE: 0.5,
            CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
        },
        CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
    }

    await hass.async_block_till_done()
    assert hass.states.get("sensor.my_daily_energy_sensor_energy")


async def test_daily_energy_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "My daily energy sensor",
            CONF_SENSOR_TYPE: SensorType.DAILY_ENERGY,
            CONF_DAILY_FIXED_ENERGY: {CONF_VALUE: 50},
        },
    )

    result = await initialize_options_flow(hass, entry)

    user_input = {CONF_VALUE: 75, CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert (
        entry.data[CONF_DAILY_FIXED_ENERGY][CONF_UNIT_OF_MEASUREMENT]
        == UnitOfPower.WATT
    )
    assert entry.data[CONF_DAILY_FIXED_ENERGY][CONF_VALUE] == 75
