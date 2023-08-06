import voluptuous as vol
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_ENTITY_ID, CONF_UNIQUE_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import SelectSelector

from custom_components.powercalc import DOMAIN
from custom_components.powercalc.config_flow import (
    CONF_CONFIRM_AUTODISCOVERED_MODEL,
    MENU_OPTION_LIBRARY,
)
from custom_components.powercalc.const import (
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_SENSOR_TYPE,
    CalculationStrategy,
    SensorType,
)
from custom_components.test.light import MockLight
from tests.common import create_mock_light_entity
from tests.config_flow.common import (
    DEFAULT_UNIQUE_ID,
    create_mock_entry,
    goto_virtual_power_strategy_step,
    initialize_options_flow,
    set_virtual_power_configuration,
)
from tests.conftest import MockEntityWithModel


async def test_manually_setup_from_library(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    mock_entity_with_model_information(
        "light.test",
        "ikea",
        "LED1545G12",
        unique_id=DEFAULT_UNIQUE_ID,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": MENU_OPTION_LIBRARY},
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "virtual_power"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "light.test"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "library"

    result = await set_virtual_power_configuration(
        hass,
        result,
        {CONF_CONFIRM_AUTODISCOVERED_MODEL: True},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_manufacturer_listing_is_filtered_by_entity_domain(
    hass: HomeAssistant,
) -> None:
    light_entity = MockLight("test", STATE_ON, DEFAULT_UNIQUE_ID)
    await create_mock_light_entity(hass, light_entity)

    result = await goto_virtual_power_strategy_step(hass, CalculationStrategy.LUT)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "manufacturer"
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "sonos", "label": "sonos"} not in manufacturer_options
    assert {"value": "signify", "label": "signify"} in manufacturer_options


async def test_manufacturer_listing_is_filtered_by_entity_domain2(
    hass: HomeAssistant,
) -> None:
    result = await goto_virtual_power_strategy_step(
        hass,
        CalculationStrategy.LUT,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_MODE: CalculationStrategy.LUT,
            CONF_UNIQUE_ID: DEFAULT_UNIQUE_ID,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "manufacturer"
    data_schema: vol.Schema = result["data_schema"]
    manufacturer_select: SelectSelector = data_schema.schema["manufacturer"]
    manufacturer_options = manufacturer_select.config["options"]
    assert {"value": "sonos", "label": "sonos"} not in manufacturer_options
    assert {"value": "shelly", "label": "shelly"} in manufacturer_options


async def test_library_options_flow_raises_error_on_non_existing_power_profile(
    hass: HomeAssistant,
) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_ENTITY_ID: "light.spots_kitchen",
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_MANUFACTURER: "foo",
            CONF_MODEL: "bar",
        },
    )

    result = await initialize_options_flow(hass, entry)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"not_supported": "Power profile could not be loaded"}
