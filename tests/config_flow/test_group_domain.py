from homeassistant import data_entry_flow
from homeassistant.const import CONF_DOMAIN
from homeassistant.core import HomeAssistant

from custom_components.powercalc import CONF_CREATE_ENERGY_SENSOR, CONF_CREATE_UTILITY_METERS, CONF_SENSOR_TYPE
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import CONF_GROUP_TYPE, GroupType, SensorType
from tests.config_flow.common import create_mock_entry


async def test_domain_group_option_menu(hass: HomeAssistant) -> None:
    """Test the domain group option menu."""
    entry = create_mock_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_TYPE: GroupType.DOMAIN,
            CONF_DOMAIN: "light",
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: False,
        },
    )

    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == Step.INIT
    assert result["menu_options"] == [Step.BASIC_OPTIONS, Step.GROUP_DOMAIN]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": Step.GROUP_DOMAIN},
    )

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_DOMAIN: "switch",
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_DOMAIN] == "switch"
