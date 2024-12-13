from homeassistant import data_entry_flow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_SENSOR_TYPE,
)
from homeassistant.core import HomeAssistant

from custom_components.powercalc import SensorType
from custom_components.powercalc.config_flow import Step
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_GROUP_TYPE,
    CONF_SUBTRACT_ENTITIES,
    GroupType,
)
from tests.config_flow.common import (
    create_mock_entry,
    initialize_options_flow,
    select_menu_item,
)


async def test_subtract_group_flow(hass: HomeAssistant) -> None:
    """Test the subtract group flow."""
    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_SUBTRACT)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    user_input = {
        CONF_NAME: "My group sensor",
        CONF_ENTITY_ID: "sensor.outlet_power",
        CONF_SUBTRACT_ENTITIES: ["sensor.light_power"],
        CONF_CREATE_UTILITY_METERS: False,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_GROUP_TYPE: GroupType.SUBTRACT,
        CONF_NAME: "My group sensor",
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: False,
        CONF_ENTITY_ID: "sensor.outlet_power",
        CONF_SUBTRACT_ENTITIES: ["sensor.light_power"],
    }
    config_entry: ConfigEntry = result["result"]

    power_state = hass.states.get("sensor.my_group_sensor_power")
    assert power_state

    result = await hass.config_entries.options.async_init(
        config_entry.entry_id,
        data=None,
    )

    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert Step.BASIC_OPTIONS in result["menu_options"]
    assert Step.GROUP_CUSTOM not in result["menu_options"]
    assert Step.UTILITY_METER_OPTIONS not in result["menu_options"]


async def test_options_flow(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "My group sensor",
            CONF_ENTITY_ID: "sensor.outlet1",
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_TYPE: GroupType.SUBTRACT,
            CONF_SUBTRACT_ENTITIES: ["sensor.light_power"],
        },
    )

    result = await initialize_options_flow(hass, entry, Step.GROUP_SUBTRACT)

    user_input = {
        CONF_ENTITY_ID: "sensor.outlet2",
        CONF_SUBTRACT_ENTITIES: ["sensor.light_power", "sensor.light_power2"],
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_SUBTRACT_ENTITIES] == ["sensor.light_power", "sensor.light_power2"]
    assert entry.data[CONF_ENTITY_ID] == "sensor.outlet2"
