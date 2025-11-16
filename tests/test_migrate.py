from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.powercalc import CONF_DISCOVERY_EXCLUDE_SELF_USAGE_DEPRECATED, DOMAIN
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
