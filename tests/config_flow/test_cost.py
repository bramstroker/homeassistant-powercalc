from homeassistant import config_entries, data_entry_flow
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_SENSOR_TYPE,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
import pytest

from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CREATE_COST_SENSOR,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_SENSOR,
    CONF_ENERGY_SENSOR_ID,
    CONF_FIXED,
    CONF_MODE,
    CONF_POWER,
    DOMAIN,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.flow_helper.schema import SECTION_COST_PRICING, build_cost_pricing_schema
from tests.common import (
    assert_entity_state,
    create_mock_config_entry,
    mock_entities_in_registry,
    run_powercalc_setup,
    set_states,
)
from tests.config_flow.common import (
    handle_options_flow_update,
    initialize_options_flow,
    select_menu_item,
    submit_options_step,
)

_KWH = {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR}


def _mock_energy_sensor(hass: HomeAssistant) -> None:
    mock_entities_in_registry(
        hass,
        {
            "sensor.existing_energy": {},
        },
    )


async def test_cost_flow_requires_a_price(hass: HomeAssistant) -> None:
    """Without a global price, the flow requires a price to be set on the sensor itself."""
    _mock_energy_sensor(hass)
    await run_powercalc_setup(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": Step.COST})
    assert result["step_id"] == Step.COST

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Fridge",
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cost_price_mandatory"}


async def test_cost_flow_creates_sensor_with_own_price(hass: HomeAssistant) -> None:
    """A price set on the cost sensor itself is used when no global price is configured."""
    _mock_energy_sensor(hass)
    hass.config.currency = "EUR"
    await run_powercalc_setup(hass)

    result = await select_menu_item(hass, Step.COST)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Fridge",
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
            SECTION_COST_PRICING: {CONF_ENERGY_PRICE: 0.4},
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENERGY_PRICE] == 0.4

    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])  # baseline
    await set_states(hass, [("sensor.existing_energy", "20", _KWH)])  # +10 kWh * 0.40
    assert float(hass.states.get("sensor.fridge_cost").state) == pytest.approx(4)


async def test_cost_options_flow_price_override(hass: HomeAssistant) -> None:
    """The energy price of an existing cost sensor entry can be overridden via the options flow."""
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
        {
            CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
            SECTION_COST_PRICING: {CONF_ENERGY_PRICE: 0.5},
        },
    )

    assert entry.data[CONF_ENERGY_PRICE] == 0.5

    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])  # baseline
    await set_states(hass, [("sensor.existing_energy", "20", _KWH)])  # +10 kWh * 0.50
    assert float(hass.states.get("sensor.fridge_cost").state) == pytest.approx(5)


async def test_virtual_power_cost_options_flow(hass: HomeAssistant) -> None:
    """A powercalc sensor with cost sensors enabled exposes a per sensor price override."""
    hass.config.currency = "EUR"
    await run_powercalc_setup(hass, None, {CONF_ENERGY_PRICE: 0.25})

    entry = await create_mock_config_entry(
        hass,
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "light.test",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_CREATE_COST_SENSOR: True,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    result = await initialize_options_flow(hass, entry, Step.COST_OPTIONS)
    assert result["step_id"] == Step.COST_OPTIONS

    result = await submit_options_step(hass, result, {CONF_ENERGY_PRICE: 0.75})
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_ENERGY_PRICE] == 0.75


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

    assert_entity_state(hass, "sensor.fridge_cost", attributes={ATTR_UNIT_OF_MEASUREMENT: "EUR"})

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


def _price_sensor_selector_config(hass: HomeAssistant, current_entity_id: str | None = None) -> dict:
    """Return the selector config of the energy price sensor field."""
    schema = build_cost_pricing_schema(hass, current_entity_id)
    return schema.schema[CONF_ENERGY_PRICE_SENSOR].config  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "unit",
    ["€/kWh", "EUR/kWh", "ct/kWh", "EUR/MWh"],
)
async def test_energy_price_sensor_selector_filters_on_price_units(hass: HomeAssistant, unit: str) -> None:
    """The picker lists price sensors by their `<currency>/<energy>` unit.

    Filtering on the `monetary` device class instead listed only cost sensors, since price
    sensors have no device class at all, see #4422.
    """
    await set_states(hass, [("sensor.energy_price", "0.32", {ATTR_UNIT_OF_MEASUREMENT: unit})])
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])

    config = _price_sensor_selector_config(hass)

    assert config["filter"] == [{"domain": ["sensor"], ATTR_UNIT_OF_MEASUREMENT: [unit]}]
    assert "device_class" not in config


async def test_energy_price_sensor_selector_is_unfiltered_without_price_sensors(hass: HomeAssistant) -> None:
    """Without any price sensor to filter on, all sensors are listed rather than none."""
    await set_states(hass, [("sensor.existing_energy", "10", _KWH)])

    config = _price_sensor_selector_config(hass)

    assert config["domain"] == ["sensor"]
    assert "filter" not in config


async def test_energy_price_sensor_selector_keeps_configured_sensor_visible(hass: HomeAssistant) -> None:
    """A configured price sensor without a price unit disables the filter.

    Otherwise the options flow would hide the very sensor that is currently in use.
    """
    await set_states(hass, [("sensor.energy_price", "0.32", {ATTR_UNIT_OF_MEASUREMENT: "€/kWh"})])
    await set_states(hass, [("sensor.unitless_price", "0.32", {})])

    config = _price_sensor_selector_config(hass, "sensor.unitless_price")

    assert config["domain"] == ["sensor"]
    assert "filter" not in config
