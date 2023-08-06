import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from custom_components.powercalc import DOMAIN, SensorType
from tests.config_flow.common import select_sensor_type


async def test_sensor_type_menu_displayed(hass: HomeAssistant) -> None:
    """Test a menu is diplayed with sensor type selection"""

    result: FlowResult = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == "user"


@pytest.mark.parametrize(
    "sensor_type",
    [SensorType.VIRTUAL_POWER, SensorType.DAILY_ENERGY, SensorType.GROUP],
)
async def test_sensor_type_form_displayed(
    hass: HomeAssistant,
    sensor_type: SensorType,
) -> None:
    await select_sensor_type(hass, sensor_type)
