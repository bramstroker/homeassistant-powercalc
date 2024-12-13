import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from custom_components.powercalc import DOMAIN
from custom_components.powercalc.config_flow import Step
from tests.config_flow.common import select_menu_item


async def test_sensor_type_menu_displayed(hass: HomeAssistant) -> None:
    """Test a menu is displayed with sensor type selection"""

    result: FlowResult = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == Step.USER


@pytest.mark.parametrize(
    "menu_item",
    [Step.VIRTUAL_POWER, Step.DAILY_ENERGY, Step.MENU_GROUP],
)
async def test_sensor_type_form_displayed(
    hass: HomeAssistant,
    menu_item: Step,
) -> None:
    await select_menu_item(hass, menu_item)
