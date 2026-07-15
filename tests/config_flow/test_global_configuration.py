import asyncio
from datetime import timedelta
from typing import Any

from homeassistant import config_entries, data_entry_flow
from homeassistant.components.utility_meter.const import DAILY
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENABLED, CONF_ENTITY_ID, CONF_NAME, CONF_UNIQUE_ID, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import (
    CONF_CREATE_STANDBY_GROUP,
    CONF_DISCOVERY,
    CONF_ENABLE_ANALYTICS,
    CONF_EXCLUDE_DEVICE_TYPES,
    CONF_EXCLUDE_SELF_USAGE,
    CONF_GROUP_ENERGY_UPDATE_INTERVAL,
    CONF_GROUP_POWER_UPDATE_INTERVAL,
    DeviceType,
)
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_APPLY_TO_ALL,
    CONF_COST_SENSOR_NAMING,
    CONF_CREATE_COST_SENSOR,
    CONF_CREATE_COST_SENSORS,
    CONF_CREATE_DOMAIN_GROUPS,
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISABLE_LIBRARY_DOWNLOAD,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_PRICE_MULTIPLIER,
    CONF_ENERGY_PRICE_SENSOR,
    CONF_ENERGY_PRICE_SURCHARGE,
    CONF_ENERGY_SENSOR_CATEGORY,
    CONF_ENERGY_SENSOR_NAMING,
    CONF_ENERGY_SENSOR_PRECISION,
    CONF_ENERGY_SENSOR_UNIT_PREFIX,
    CONF_ENERGY_UPDATE_INTERVAL,
    CONF_FIXED,
    CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_MODE,
    CONF_POWER,
    CONF_POWER_SENSOR_CATEGORY,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_POWER_SENSOR_PRECISION,
    CONF_POWER_UPDATE_INTERVAL,
    CONF_SENSOR_TYPE,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_OFFSET,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DEFAULT_ENERGY_INTEGRATION_METHOD,
    DEFAULT_ENERGY_NAME_PATTERN,
    DEFAULT_ENERGY_SENSOR_PRECISION,
    DEFAULT_ENTITY_CATEGORY,
    DEFAULT_POWER_NAME_PATTERN,
    DEFAULT_POWER_SENSOR_PRECISION,
    DEFAULT_UTILITY_METER_TYPES,
    DOMAIN,
    DOMAIN_CONFIG,
    ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    CalculationStrategy,
    SensorType,
    UnitPrefix,
)
from custom_components.powercalc.flow_helper.schema import SECTION_COST_NAMING, SECTION_COST_PRICING
from tests.common import (
    assert_entity_state,
    create_mock_config_entry,
    get_simple_fixed_config,
    run_powercalc_setup,
    set_states,
)
from tests.config_flow.common import (
    handle_options_flow_update,
    initialize_options_flow,
    select_menu_item,
    submit_form_step,
    submit_options_step,
)


async def test_config_flow(hass: HomeAssistant) -> None:
    """Test full configuration flow."""
    await run_powercalc_setup(hass)

    result = await select_menu_item(hass, Step.GLOBAL_CONFIGURATION)

    result = await submit_form_step(
        hass,
        result,
        {
            CONF_DISABLE_LIBRARY_DOWNLOAD: True,
            CONF_CREATE_ENERGY_SENSORS: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_POWER_SENSOR_PRECISION: 4,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_DISCOVERY

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EXCLUDE_DEVICE_TYPES: [DeviceType.SMART_SWITCH],
        },
    )

    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_THROTTLING
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ENERGY_UPDATE_INTERVAL: 20,
        },
    )

    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_ENERGY

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_UTILITY_METER

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_UTILITY_METER_TARIFFS: ["foo"],
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ENABLE_ANALYTICS: False,
        CONF_CREATE_DOMAIN_GROUPS: [],
        CONF_CREATE_STANDBY_GROUP: True,
        CONF_CREATE_ENERGY_SENSORS: True,
        CONF_CREATE_COST_SENSORS: False,
        CONF_COST_SENSOR_NAMING: "{} cost",
        CONF_CREATE_UTILITY_METERS: True,
        CONF_DISABLE_EXTENDED_ATTRIBUTES: False,
        CONF_DISABLE_LIBRARY_DOWNLOAD: True,
        CONF_DISCOVERY: {
            CONF_ENABLED: True,
            CONF_EXCLUDE_DEVICE_TYPES: [DeviceType.SMART_SWITCH],
            CONF_EXCLUDE_SELF_USAGE: False,
        },
        CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
        CONF_ENERGY_SENSOR_CATEGORY: None,
        CONF_ENERGY_SENSOR_NAMING: "{} energy",
        CONF_ENERGY_SENSOR_PRECISION: 4,
        CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.KILO,
        CONF_GROUP_ENERGY_UPDATE_INTERVAL: 0,
        CONF_GROUP_POWER_UPDATE_INTERVAL: 0,
        CONF_ENERGY_UPDATE_INTERVAL: 20,
        CONF_POWER_UPDATE_INTERVAL: 0,
        CONF_IGNORE_UNAVAILABLE_STATE: False,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        CONF_POWER_SENSOR_CATEGORY: None,
        CONF_POWER_SENSOR_NAMING: "{} power",
        CONF_POWER_SENSOR_PRECISION: 4,
        CONF_UTILITY_METER_NET_CONSUMPTION: False,
        CONF_UTILITY_METER_OFFSET: 0,
        CONF_UTILITY_METER_TARIFFS: ["foo"],
        CONF_UTILITY_METER_TYPES: [DAILY],
    }
    config_entry: ConfigEntry = result["result"]
    assert config_entry.unique_id == ENTRY_GLOBAL_CONFIG_UNIQUE_ID

    global_config = hass.data[DOMAIN][DOMAIN_CONFIG]
    assert global_config[CONF_DISABLE_LIBRARY_DOWNLOAD]
    assert global_config[CONF_POWER_SENSOR_PRECISION] == 4
    assert global_config[CONF_ENERGY_UPDATE_INTERVAL] == 20


@pytest.mark.parametrize(
    "user_input,expected_step",
    [
        (
            {CONF_CREATE_ENERGY_SENSORS: False, CONF_CREATE_UTILITY_METERS: True},
            Step.GLOBAL_CONFIGURATION_UTILITY_METER,
        ),
        ({CONF_CREATE_ENERGY_SENSORS: True, CONF_CREATE_UTILITY_METERS: True}, Step.GLOBAL_CONFIGURATION_ENERGY),
        ({CONF_CREATE_ENERGY_SENSORS: True, CONF_CREATE_UTILITY_METERS: False}, Step.GLOBAL_CONFIGURATION_ENERGY),
        ({CONF_CREATE_ENERGY_SENSORS: False, CONF_CREATE_UTILITY_METERS: False}, None),
    ],
)
async def test_energy_and_utility_options_skipped(
    hass: HomeAssistant,
    user_input: dict[str, Any],
    expected_step: Step | None,
) -> None:
    """Test the energy and utility_meter options are only shown when relevant."""
    result = await select_menu_item(hass, Step.GLOBAL_CONFIGURATION)

    result = await submit_form_step(hass, result, user_input)

    # Submit discovery step
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {},
    )

    # Submit throttling step
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {},
    )

    if expected_step:
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == expected_step
    else:
        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_initialize_options_succeeds_with_yaml_sensors_in_config(hass: HomeAssistant) -> None:
    """Test options flow is initialized when sensors are defined in YAML configuration."""
    entry = await create_mock_global_config_entry(hass, {})

    await run_powercalc_setup(hass, get_simple_fixed_config("input_boolean.test", 50))

    result = await initialize_options_flow(hass, entry, Step.GLOBAL_CONFIGURATION)
    assert result["type"] == data_entry_flow.FlowResultType.FORM


async def test_global_configuration_can_only_be_configured_once(hass: HomeAssistant) -> None:
    """Test global configuration can only be configured once."""
    await create_mock_global_config_entry(hass, {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert Step.GLOBAL_CONFIGURATION not in result["menu_options"]


async def test_basic_options_flow(hass: HomeAssistant) -> None:
    """Test basic options flow."""
    entry = await create_mock_global_config_entry(hass, {})

    await handle_options_flow_update(
        hass,
        entry,
        Step.GLOBAL_CONFIGURATION,
        {
            CONF_POWER_SENSOR_PRECISION: 4,
            CONF_POWER_SENSOR_NAMING: "{} power_watt",
            CONF_POWER_SENSOR_FRIENDLY_NAMING: "{} friendly",
            CONF_POWER_SENSOR_CATEGORY: EntityCategory.DIAGNOSTIC,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
            CONF_INCLUDE_NON_POWERCALC_SENSORS: False,
            CONF_DISABLE_EXTENDED_ATTRIBUTES: True,
            CONF_DISABLE_LIBRARY_DOWNLOAD: False,
            CONF_CREATE_ENERGY_SENSORS: False,
        },
    )

    # Check if config entry data is updated.
    assert entry.data[CONF_POWER_SENSOR_PRECISION] == 4
    assert entry.data[CONF_POWER_SENSOR_NAMING] == "{} power_watt"
    assert entry.data[CONF_POWER_SENSOR_FRIENDLY_NAMING] == "{} friendly"
    assert entry.data[CONF_POWER_SENSOR_CATEGORY] == EntityCategory.DIAGNOSTIC
    assert entry.data[CONF_IGNORE_UNAVAILABLE_STATE]
    assert not entry.data[CONF_INCLUDE_NON_POWERCALC_SENSORS]
    assert entry.data[CONF_DISABLE_EXTENDED_ATTRIBUTES]
    assert not entry.data[CONF_DISABLE_LIBRARY_DOWNLOAD]
    assert not entry.data[CONF_CREATE_ENERGY_SENSORS]

    # Check if global config in hass object is updated.
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_POWER_SENSOR_PRECISION] == 4


async def test_energy_options_flow(hass: HomeAssistant) -> None:
    """Test energy options flow."""
    entry = await create_mock_global_config_entry(
        hass,
        {
            CONF_CREATE_ENERGY_SENSORS: True,
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    await handle_options_flow_update(
        hass,
        entry,
        Step.GLOBAL_CONFIGURATION_ENERGY,
        {
            CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
            CONF_ENERGY_SENSOR_PRECISION: 5,
        },
    )

    # Check if config entry data is updated.
    assert entry.data[CONF_ENERGY_INTEGRATION_METHOD] == ENERGY_INTEGRATION_METHOD_TRAPEZODIAL
    assert entry.data[CONF_ENERGY_SENSOR_PRECISION] == 5

    # Check if global config in hass object is updated.
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_ENERGY_INTEGRATION_METHOD] == ENERGY_INTEGRATION_METHOD_TRAPEZODIAL
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_ENERGY_SENSOR_PRECISION] == 5


async def test_clear_energy_sensor_category(hass: HomeAssistant) -> None:
    """Test clearing a previously set energy sensor category is persisted.

    Regression test for https://github.com/bramstroker/homeassistant-powercalc/issues/4228
    """
    entry = await create_mock_global_config_entry(
        hass,
        {
            CONF_CREATE_ENERGY_SENSORS: True,
            CONF_ENERGY_SENSOR_CATEGORY: EntityCategory.DIAGNOSTIC,
        },
    )

    await handle_options_flow_update(
        hass,
        entry,
        Step.GLOBAL_CONFIGURATION_ENERGY,
        {
            CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
        },
    )

    # The category should no longer be set, both on the config entry and in the runtime config.
    assert CONF_ENERGY_SENSOR_CATEGORY not in entry.data
    assert not hass.data[DOMAIN][DOMAIN_CONFIG].get(CONF_ENERGY_SENSOR_CATEGORY)


async def test_utility_meter_options_flow(hass: HomeAssistant) -> None:
    """Test utility meter options flow."""
    entry = await create_mock_global_config_entry(
        hass,
        {
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    await handle_options_flow_update(
        hass,
        entry,
        Step.GLOBAL_CONFIGURATION_UTILITY_METER,
        {
            CONF_UTILITY_METER_TYPES: [DAILY],
            CONF_UTILITY_METER_TARIFFS: ["peak", "off_peak"],
            CONF_UTILITY_METER_OFFSET: 1,
            CONF_UTILITY_METER_NET_CONSUMPTION: True,
        },
    )

    # Check if config entry data is updated.
    assert entry.data[CONF_UTILITY_METER_TYPES] == [DAILY]
    assert entry.data[CONF_UTILITY_METER_TARIFFS] == ["peak", "off_peak"]
    assert entry.data[CONF_UTILITY_METER_OFFSET] == 1
    assert entry.data[CONF_UTILITY_METER_NET_CONSUMPTION]

    # Check if global config in hass object is updated.
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_UTILITY_METER_TYPES] == [DAILY]
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_UTILITY_METER_TARIFFS] == ["peak", "off_peak"]
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_UTILITY_METER_OFFSET] == timedelta(days=1)
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_UTILITY_METER_NET_CONSUMPTION]


async def test_cost_options_step_in_config_flow(hass: HomeAssistant) -> None:
    """The cost options step is shown in the wizard and the price is stored."""
    result = await select_menu_item(hass, Step.GLOBAL_CONFIGURATION)

    result = await submit_form_step(
        hass,
        result,
        {
            CONF_CREATE_ENERGY_SENSORS: False,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_CREATE_COST_SENSORS: True,
        },
    )

    # Submit discovery step
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_DISCOVERY
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    # Submit throttling step
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_THROTTLING
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    # Energy and utility meter steps are skipped, cost step is shown
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            SECTION_COST_PRICING: {
                CONF_ENERGY_PRICE: 0.30,
                CONF_ENERGY_PRICE_SURCHARGE: 0.05,
                CONF_ENERGY_PRICE_MULTIPLIER: 1.21,
            },
            SECTION_COST_NAMING: {CONF_COST_SENSOR_NAMING: "{} cost"},
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CREATE_COST_SENSORS] is True
    assert result["data"][CONF_ENERGY_PRICE] == pytest.approx(0.30)
    assert result["data"][CONF_ENERGY_PRICE_SURCHARGE] == pytest.approx(0.05)
    assert result["data"][CONF_ENERGY_PRICE_MULTIPLIER] == pytest.approx(1.21)
    assert result["data"][CONF_COST_SENSOR_NAMING] == "{} cost"


async def test_cost_options_step_skipped_when_disabled(hass: HomeAssistant) -> None:
    """The cost options step is skipped when cost sensors are disabled."""
    result = await select_menu_item(hass, Step.GLOBAL_CONFIGURATION)

    result = await submit_form_step(
        hass,
        result,
        {
            CONF_CREATE_ENERGY_SENSORS: False,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_CREATE_COST_SENSORS: False,
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_cost_options_flow(hass: HomeAssistant) -> None:
    """Test cost options flow (options flow menu + price entity)."""
    entry = await create_mock_global_config_entry(
        hass,
        {
            CONF_CREATE_COST_SENSORS: True,
        },
    )

    await handle_options_flow_update(
        hass,
        entry,
        Step.GLOBAL_CONFIGURATION_COST,
        {
            SECTION_COST_PRICING: {
                CONF_ENERGY_PRICE_SENSOR: "sensor.energy_price",
                CONF_ENERGY_PRICE_SURCHARGE: 0.05,
                CONF_ENERGY_PRICE_MULTIPLIER: 1.21,
            },
            SECTION_COST_NAMING: {CONF_COST_SENSOR_NAMING: "{} costs"},
        },
    )

    # Check if config entry data is updated.
    assert entry.data[CONF_ENERGY_PRICE_SENSOR] == "sensor.energy_price"
    assert entry.data[CONF_ENERGY_PRICE_SURCHARGE] == pytest.approx(0.05)
    assert entry.data[CONF_ENERGY_PRICE_MULTIPLIER] == pytest.approx(1.21)
    assert entry.data[CONF_COST_SENSOR_NAMING] == "{} costs"

    # Check if global config in hass object is updated.
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_ENERGY_PRICE_SENSOR] == "sensor.energy_price"
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_ENERGY_PRICE_SURCHARGE] == pytest.approx(0.05)
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_ENERGY_PRICE_MULTIPLIER] == pytest.approx(1.21)


def _create_cost_toggle_power_entry(create_cost_sensor: bool) -> MockConfigEntry:
    """Build a virtual power config entry carrying an explicit create_cost_sensor flag."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="cost-toggle-entry",
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "cost-toggle-entry",
            CONF_ENTITY_ID: "light.test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            CONF_CREATE_COST_SENSOR: create_cost_sensor,
        },
        title="Cost toggle entry",
    )


async def _toggle_cost_sensors(hass: HomeAssistant, entry: MockConfigEntry, value: bool) -> FlowResult:
    """Open the options basic step and flip create_cost_sensors, returning the resulting step."""
    result = await initialize_options_flow(hass, entry, Step.GLOBAL_CONFIGURATION)
    return await submit_options_step(hass, result, {CONF_CREATE_COST_SENSORS: value})


async def test_toggling_cost_sensors_redirects_to_apply_step(hass: HomeAssistant) -> None:
    """Flipping create_cost_sensors redirects to the dedicated apply step."""
    entry = await create_mock_global_config_entry(hass, {CONF_ENERGY_PRICE: 0.25})

    result = await _toggle_cost_sensors(hass, entry, value=True)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST_APPLY


async def test_no_apply_step_when_cost_toggle_unchanged(hass: HomeAssistant) -> None:
    """Not touching create_cost_sensors persists directly without the apply step."""
    entry = await create_mock_global_config_entry(hass, {CONF_ENERGY_PRICE: 0.25, CONF_CREATE_COST_SENSORS: True})

    result = await _toggle_cost_sensors(hass, entry, value=True)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_apply_to_all_enables_cost_sensor_on_existing_entries(hass: HomeAssistant) -> None:
    """Enabling cost sensors + apply toggle turns on create_cost_sensor for all config entries."""
    power_entry = _create_cost_toggle_power_entry(create_cost_sensor=False)
    power_entry.add_to_hass(hass)

    entry = await create_mock_global_config_entry(hass, {CONF_ENERGY_PRICE: 0.25})

    result = await _toggle_cost_sensors(hass, entry, value=True)
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST_APPLY

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_APPLY_TO_ALL: True},
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    updated = hass.config_entries.async_get_entry(power_entry.entry_id)
    assert updated.data[CONF_CREATE_COST_SENSOR] is True
    # The transient toggle itself is not persisted to the global config.
    assert CONF_APPLY_TO_ALL not in hass.data[DOMAIN][DOMAIN_CONFIG]


async def test_disabling_cost_sensors_applies_to_all(hass: HomeAssistant) -> None:
    """Disabling cost sensors + apply toggle turns off create_cost_sensor for all config entries."""
    power_entry = _create_cost_toggle_power_entry(create_cost_sensor=True)
    power_entry.add_to_hass(hass)

    entry = await create_mock_global_config_entry(
        hass,
        {CONF_ENERGY_PRICE: 0.25, CONF_CREATE_COST_SENSORS: True},
    )

    result = await _toggle_cost_sensors(hass, entry, value=False)
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST_APPLY

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_APPLY_TO_ALL: True},
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    updated = hass.config_entries.async_get_entry(power_entry.entry_id)
    assert updated.data[CONF_CREATE_COST_SENSOR] is False


async def test_existing_entries_untouched_without_apply_to_all(hass: HomeAssistant) -> None:
    """Existing config entries keep their create_cost_sensor flag when the apply toggle is off."""
    power_entry = _create_cost_toggle_power_entry(create_cost_sensor=False)
    power_entry.add_to_hass(hass)

    entry = await create_mock_global_config_entry(hass, {CONF_ENERGY_PRICE: 0.25})

    result = await _toggle_cost_sensors(hass, entry, value=True)
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST_APPLY

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_APPLY_TO_ALL: False},
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    updated = hass.config_entries.async_get_entry(power_entry.entry_id)
    assert updated.data[CONF_CREATE_COST_SENSOR] is False


async def test_cost_step_requires_a_price_in_config_flow(hass: HomeAssistant) -> None:
    """Submitting the cost step without a price shows a validation error."""
    result = await select_menu_item(hass, Step.GLOBAL_CONFIGURATION)

    result = await submit_form_step(
        hass,
        result,
        {
            CONF_CREATE_ENERGY_SENSORS: False,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_CREATE_COST_SENSORS: True,
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST

    # Submit without a price or price sensor.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {SECTION_COST_PRICING: {}, SECTION_COST_NAMING: {}},
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST
    assert result["errors"] == {"base": "cost_price_mandatory"}

    # Supplying a price now completes the flow.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {SECTION_COST_PRICING: {CONF_ENERGY_PRICE: 0.30}, SECTION_COST_NAMING: {}},
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENERGY_PRICE] == pytest.approx(0.30)


async def test_cost_step_requires_a_price_in_options_flow(hass: HomeAssistant) -> None:
    """Submitting the cost options step without a price shows a validation error."""
    entry = await create_mock_global_config_entry(
        hass,
        {
            CONF_CREATE_COST_SENSORS: True,
        },
    )

    result = await initialize_options_flow(hass, entry, Step.GLOBAL_CONFIGURATION_COST)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {SECTION_COST_PRICING: {}, SECTION_COST_NAMING: {}},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST
    assert result["errors"] == {"base": "cost_price_mandatory"}


async def test_enabling_cost_sensors_without_price_continues_to_price_step(hass: HomeAssistant) -> None:
    """Enabling cost sensors without a price: apply step first, then the cost/price step."""
    entry = await create_mock_global_config_entry(hass, {})

    result = await _toggle_cost_sensors(hass, entry, value=True)

    # First the apply step is shown (the toggle was flipped).
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST_APPLY

    # No price configured yet, so after the apply step the cost/price step follows.
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.GLOBAL_CONFIGURATION_COST

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {SECTION_COST_PRICING: {CONF_ENERGY_PRICE: 0.30}, SECTION_COST_NAMING: {}},
    )
    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_CREATE_COST_SENSORS] is True
    assert entry.data[CONF_ENERGY_PRICE] == pytest.approx(0.30)
    assert hass.data[DOMAIN][DOMAIN_CONFIG][CONF_ENERGY_PRICE] == pytest.approx(0.30)


async def test_discovery_options_flow(hass: HomeAssistant) -> None:
    """Test discovery options flow."""
    entry = await create_mock_global_config_entry(hass, {})

    await handle_options_flow_update(
        hass,
        entry,
        Step.GLOBAL_CONFIGURATION_DISCOVERY,
        {
            CONF_ENABLED: True,
            CONF_EXCLUDE_SELF_USAGE: True,
            CONF_EXCLUDE_DEVICE_TYPES: [DeviceType.SMART_SWITCH],
        },
    )

    # Check if config entry data is updated.
    discovery_options = entry.data[CONF_DISCOVERY]
    assert discovery_options[CONF_ENABLED]
    assert discovery_options[CONF_EXCLUDE_SELF_USAGE]
    assert discovery_options[CONF_EXCLUDE_DEVICE_TYPES] == [DeviceType.SMART_SWITCH]


async def test_throttling_options_flow(hass: HomeAssistant) -> None:
    """Test throttling options flow."""
    entry = await create_mock_global_config_entry(hass, {})

    await handle_options_flow_update(
        hass,
        entry,
        Step.GLOBAL_CONFIGURATION_THROTTLING,
        {
            CONF_ENERGY_UPDATE_INTERVAL: 20,
            CONF_GROUP_POWER_UPDATE_INTERVAL: 15,
            CONF_GROUP_ENERGY_UPDATE_INTERVAL: 30,
        },
    )

    # Check if config entry data is updated.
    assert entry.data[CONF_ENERGY_UPDATE_INTERVAL] == 20
    assert entry.data[CONF_GROUP_POWER_UPDATE_INTERVAL] == 15
    assert entry.data[CONF_GROUP_ENERGY_UPDATE_INTERVAL] == 30


async def test_entities_are_reloaded_reflecting_changes(hass: HomeAssistant) -> None:
    """Test entities are reloaded reflecting changes."""

    await set_states(hass, [("light.test", STATE_ON)])

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_NAME: "Test",
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
        },
    )

    global_config_entry = await create_mock_global_config_entry(
        hass,
        {
            CONF_CREATE_ENERGY_SENSORS: True,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED: 1200,
        },
    )

    await run_powercalc_setup(hass)

    assert_entity_state(hass, "sensor.test_power", "50.00")

    await handle_options_flow_update(
        hass,
        global_config_entry,
        Step.GLOBAL_CONFIGURATION,
        {CONF_POWER_SENSOR_PRECISION: 4},
    )
    await asyncio.sleep(0.1)

    assert_entity_state(hass, "sensor.test_power", "50.0000")


async def create_mock_global_config_entry(hass: HomeAssistant, data: dict[str, Any]) -> MockConfigEntry:
    """Create a mock entry."""
    return await create_mock_config_entry(
        hass,
        {
            CONF_POWER_SENSOR_NAMING: DEFAULT_POWER_NAME_PATTERN,
            CONF_POWER_SENSOR_PRECISION: DEFAULT_POWER_SENSOR_PRECISION,
            CONF_POWER_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
            CONF_ENERGY_INTEGRATION_METHOD: DEFAULT_ENERGY_INTEGRATION_METHOD,
            CONF_ENERGY_SENSOR_NAMING: DEFAULT_ENERGY_NAME_PATTERN,
            CONF_ENERGY_SENSOR_PRECISION: DEFAULT_ENERGY_SENSOR_PRECISION,
            CONF_ENERGY_SENSOR_CATEGORY: DEFAULT_ENTITY_CATEGORY,
            CONF_ENERGY_SENSOR_UNIT_PREFIX: UnitPrefix.KILO,
            CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED: 600,
            CONF_DISABLE_EXTENDED_ATTRIBUTES: False,
            CONF_IGNORE_UNAVAILABLE_STATE: False,
            CONF_CREATE_DOMAIN_GROUPS: [],
            CONF_CREATE_ENERGY_SENSORS: True,
            CONF_CREATE_UTILITY_METERS: False,
            CONF_DISCOVERY: {CONF_ENABLED: True},
            CONF_UTILITY_METER_OFFSET: 0,
            CONF_UTILITY_METER_TYPES: DEFAULT_UTILITY_METER_TYPES,
            CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
            **data,
        },
        unique_id=ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
        setup=False,
    )
