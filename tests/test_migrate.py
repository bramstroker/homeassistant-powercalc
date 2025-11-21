from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.powercalc import (
    CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED,
    CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED,
    CONF_GROUP_UPDATE_INTERVAL_DEPRECATED,
    DOMAIN,
)
from custom_components.powercalc.const import CONF_ENERGY_UPDATE_INTERVAL, CONF_GROUP_ENERGY_UPDATE_INTERVAL
from tests.common import run_powercalc_setup


async def test_legacy_discovery_config_raises_issue(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED: True,
        },
    )

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, "legacy_discovery_config")
    assert issue


async def test_legacy_update_interval_config_raises_issue(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        {},
        {
            CONF_GROUP_UPDATE_INTERVAL_DEPRECATED: 80,
            CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED: timedelta(minutes=15),
        },
    )

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, "legacy_update_interval_config")
    assert issue

    global_config = hass.data[DOMAIN]["config"]
    assert global_config[CONF_GROUP_ENERGY_UPDATE_INTERVAL] == 80
    assert global_config[CONF_ENERGY_UPDATE_INTERVAL] == 900
    assert CONF_GROUP_UPDATE_INTERVAL_DEPRECATED not in global_config
    assert CONF_FORCE_UPDATE_FREQUENCY_DEPRECATED not in global_config
