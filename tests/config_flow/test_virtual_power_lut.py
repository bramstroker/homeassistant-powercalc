import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.light import ColorMode
from homeassistant.const import CONF_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import SelectSelector

from custom_components.powercalc.config_flow import CONF_CONFIRM_AUTODISCOVERED_MODEL, Step
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_SENSOR_TYPE,
    CONF_SUB_PROFILE,
    CalculationStrategy,
    SensorType,
)
from custom_components.test.light import MockLight
from tests.common import create_mock_light_entity
from tests.config_flow.common import (
    DEFAULT_UNIQUE_ID,
    assert_default_virtual_power_entry_data,
    confirm_auto_discovered_model,
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    set_virtual_power_configuration,
)
from tests.conftest import MockEntityWithModel


async def test_lut_manual_flow(hass: HomeAssistant) -> None:
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    light_entity.supported_color_modes = [ColorMode.COLOR_TEMP, ColorMode.HS]
    light_entity.color_mode = ColorMode.COLOR_TEMP
    await create_mock_light_entity(hass, light_entity)

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "belkin", "label": "belkin"} in manufacturer_options
    assert {"value": "signify", "label": "signify"} in manufacturer_options

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MANUFACTURER: "signify"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MODEL
    data_schema: vol.Schema = result["data_schema"]
    model_select: SelectSelector = data_schema.schema["model"]
    model_options = model_select.config["options"]
    assert {"value": "LCT010", "label": "LCT010"} in model_options
    assert {"value": "LWB010", "label": "LWB010"} in model_options

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MODEL: "LCT010"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM

    # Advanced options step
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    assert_default_virtual_power_entry_data(
        CalculationStrategy.LUT,
        result["data"],
        {CONF_MANUFACTURER: "signify", CONF_MODEL: "LCT010"},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_lut_autodiscover_flow(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    manufacturer = "ikea"
    model = "LED1545G12"
    mock_entity_with_model_information(
        "light.test",
        manufacturer,
        model,
        unique_id=DEFAULT_UNIQUE_ID,
    )

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.LIBRARY
    assert result["description_placeholders"] == {
        "manufacturer": "ikea",
        "model": "LED1545G12",
        "remarks": None,
        "source": "Source entity: light.test",
    }

    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.LUT,
        result["data"],
        {CONF_MANUFACTURER: manufacturer, CONF_MODEL: model},
    )

    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_power")
    assert hass.states.get("sensor.test_energy")


async def test_lut_not_autodiscovered_model_unsupported(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information("light.test", "ikea", "unknown_model")

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER


async def test_lut_not_autodiscovered(hass: HomeAssistant) -> None:
    light_entity = MockLight("test", STATE_ON)
    light_entity._attr_unique_id = None  # noqa
    await create_mock_light_entity(hass, light_entity)

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER


async def test_lut_autodiscover_flow_not_confirmed(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    When manufacturer and model are auto detected and user chooses to not accept it,
    make sure he/she is forwarded to the manufacturer listing
    """
    mock_entity_with_model_information(
        "light.test",
        "ikea",
        "LED1545G12",
        unique_id="234438",
    )

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.LIBRARY

    result = await confirm_auto_discovered_model(hass, result, confirmed=False)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.MANUFACTURER


async def test_lut_flow_with_sub_profiles(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information("light.test", "", "")

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MANUFACTURER: "yeelight"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MODEL: "YLDL01YL"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.SUB_PROFILE
    data_schema: vol.Schema = result["data_schema"]
    model_select: SelectSelector = data_schema.schema["sub_profile"]
    select_options = model_select.config["options"]
    assert {"value": "ambilight", "label": "ambilight"} in select_options
    assert {"value": "downlight", "label": "downlight"} in select_options

    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_SUB_PROFILE: "ambilight"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert_default_virtual_power_entry_data(
        CalculationStrategy.LUT,
        result["data"],
        {CONF_MANUFACTURER: "yeelight", CONF_MODEL: "YLDL01YL/ambilight"},
    )


async def test_lut_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.spots_kitchen",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MODE: CalculationStrategy.LUT,
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT010",
        },
    )

    result = await initialize_options_flow(hass, entry, Step.BASIC_OPTIONS)

    user_input = {CONF_CREATE_ENERGY_SENSOR: False}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert not entry.data[CONF_CREATE_ENERGY_SENSOR]
