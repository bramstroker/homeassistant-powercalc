from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.powercalc.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    diagnostics_data = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert diagnostics_data == {
        "entry": mock_config_entry.as_dict()
    }
