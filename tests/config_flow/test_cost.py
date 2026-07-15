from homeassistant import config_entries, data_entry_flow
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_SENSOR_TYPE,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import RegistryEntryWithDefaults, mock_registry

from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_ENERGY_PRICE,
    CONF_ENERGY_SENSOR_ID,
    DOMAIN,
    SensorType,
)
from tests.common import create_mock_config_entry, run_powercalc_setup, set_states
from tests.config_flow.common import handle_options_flow_update, select_menu_item

_KWH = {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR}


def _mock_energy_sensor(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "sensor.existing_energy": RegistryEntryWithDefaults(
                entity_id="sensor.existing_energy",
                unique_id="1234",
                platform="sensor",
            ),
        },
    )


async def test_cost_flow_aborts_without_global_price(hass: HomeAssistant) -> None:
    """The cost flow aborts and points to global configuration when no price is configured."""
    await run_powercalc_setup(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": Step.COST})

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "cost_no_global_price"


async def test_cost_flow_creates_sensor(hass: HomeAssistant) -> None:
    """A standalone cost sensor is created for an existing energy sensor and accumulates cost."""
    _mock_energy_sensor(hass)
    hass.config.currency = "EUR"
    await run_powercalc_setup(hass, None, {CONF_ENERGY_PRICE: 0.25})

    result = await select_menu_item(hass, Step.COST)
    assert result["step_id"] == Step.COST

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Fridge",
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SENSOR_TYPE] == SensorType.COST
    assert result["data"][CONF_ENERGY_SENSOR_ID] == "sensor.existing_energy"

    cost_state = hass.states.get("sensor.fridge_cost")
    assert cost_state
    assert cost_state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "EUR"

    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])  # baseline
    await set_states(hass, [("sensor.existing_energy", "20", _KWH)])  # +10 kWh * 0.25
    assert float(hass.states.get("sensor.fridge_cost").state) == pytest.approx(2.5)


async def test_cost_options_flow(hass: HomeAssistant) -> None:
    """The energy sensor of an existing cost sensor entry can be changed via the options flow."""
    _mock_energy_sensor(hass)
    hass.config.currency = "EUR"
    await run_powercalc_setup(hass, None, {CONF_ENERGY_PRICE: 0.25})

    entry = await create_mock_config_entry(
        hass,
        {
            CONF_NAME: "Fridge",
            CONF_SENSOR_TYPE: SensorType.COST,
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
        },
    )

    await handle_options_flow_update(
        hass,
        entry,
        Step.COST,
        {CONF_ENERGY_SENSOR_ID: "sensor.other_energy"},
    )

    assert entry.data[CONF_ENERGY_SENSOR_ID] == "sensor.other_energy"
