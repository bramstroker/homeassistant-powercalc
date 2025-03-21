from selectors import SelectSelector

from homeassistant import data_entry_flow
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant

from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_MANUFACTURER,
)
from tests.config_flow.common import confirm_auto_discovered_model, select_menu_item
from tests.conftest import MockEntityWithModel


async def test_lightify_plug_selectable(
    hass: HomeAssistant,
    mock_entity_with_model_information: MockEntityWithModel,
) -> None:
    """
    See https://github.com/bramstroker/homeassistant-powercalc/issues/2858
    """
    mock_entity_with_model_information(
        "light.test",
        "osram",
        "LIGHTIFY Plug 01",
        platform="osramlightify",
    )

    result = await select_menu_item(hass, Step.MENU_LIBRARY)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ENTITY_ID: "light.test"},
    )
    result = await confirm_auto_discovered_model(hass, result, confirmed=False)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_MANUFACTURER: "osram",
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    data_schema = result["data_schema"]
    model_select: SelectSelector = data_schema.schema["model"]
    model_options = model_select.config["options"]
    assert {"value": "LIGHTIFY Plug 01", "label": "LIGHTIFY Plug 01"} in model_options
