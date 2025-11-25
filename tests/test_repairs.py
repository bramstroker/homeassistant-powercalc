from homeassistant.components.repairs import RepairsFlowManager
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.powercalc import CONF_SENSOR_TYPE, DOMAIN, SensorType
from custom_components.powercalc.const import CONF_MANUFACTURER, CONF_MODEL
from tests.common import get_test_config_dir, setup_config_entry


async def test_sub_profile_repair(hass: HomeAssistant, issue_registry: ir.IssueRegistry) -> None:
    """Test sub profile repair"""
    hass.config.config_dir = get_test_config_dir()
    config_entry = await setup_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "sub_profile",
        },
    )

    issue = issue_registry.async_get_issue("powercalc", f"sub_profile_{config_entry.entry_id}")
    assert issue

    # Dispatch repair flow and see if we can change the sub_profile
    # After the repair, the config entry should have the new sub_profile set in the data
    assert await async_setup_component(hass, "repairs", {})
    flow_manager = RepairsFlowManager(hass)
    result = await flow_manager.async_init(DOMAIN, data={"issue_id": issue.issue_id})
    assert result["type"] == "form"
    assert result["step_id"] == "sub_profile"

    result = await flow_manager.async_configure(result["flow_id"], user_input={"sub_profile": "a"})
    assert result["type"] == "create_entry"

    assert config_entry.data[CONF_MODEL] == "sub_profile/a"


async def test_no_sub_profile_repair_raised(hass: HomeAssistant, issue_registry: ir.IssueRegistry) -> None:
    hass.config.config_dir = get_test_config_dir()
    config_entry = await setup_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "sub_profile_matchers",
        },
    )

    issue = issue_registry.async_get_issue("powercalc", f"sub_profile_{config_entry.entry_id}")
    assert not issue
