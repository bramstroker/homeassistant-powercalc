from typing import Any

import pytest
from homeassistant import data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.powercalc.config_flow import Steps
from custom_components.powercalc.const import (
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_DISABLE_LIBRARY_DOWNLOAD,
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_UTILITY_METER_NET_CONSUMPTION,
    CONF_UTILITY_METER_TARIFFS,
    ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
)
from tests.config_flow.common import (
    select_menu_item,
)


async def test_config_flow(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Steps.GLOBAL_CONFIGURATION)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_DISABLE_LIBRARY_DOWNLOAD: True,
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Steps.GLOBAL_CONFIGURATION_ENERGY

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Steps.GLOBAL_CONFIGURATION_UTILITY_METER

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_UTILITY_METER_TARIFFS: ["foo"],
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_UTILITY_METERS: True,
        CONF_DISABLE_EXTENDED_ATTRIBUTES: False,
        CONF_DISABLE_LIBRARY_DOWNLOAD: True,
        CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
        CONF_IGNORE_UNAVAILABLE_STATE: False,
        CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
        CONF_UTILITY_METER_NET_CONSUMPTION: False,
        CONF_UTILITY_METER_TARIFFS: ["foo"],
    }


@pytest.mark.parametrize(
    "user_input,expected_step",
    [
        ({CONF_CREATE_ENERGY_SENSOR: False, CONF_CREATE_UTILITY_METERS: True}, Steps.GLOBAL_CONFIGURATION_UTILITY_METER),
        ({CONF_CREATE_ENERGY_SENSOR: True, CONF_CREATE_UTILITY_METERS: True}, Steps.GLOBAL_CONFIGURATION_ENERGY),
        ({CONF_CREATE_ENERGY_SENSOR: True, CONF_CREATE_UTILITY_METERS: False}, Steps.GLOBAL_CONFIGURATION_ENERGY),
        ({CONF_CREATE_ENERGY_SENSOR: False, CONF_CREATE_UTILITY_METERS: False}, None),
    ],
)
async def test_energy_and_utility_options_skipped(hass: HomeAssistant, user_input: dict[str, Any], expected_step: Steps | None) -> None:
    result = await select_menu_item(hass, Steps.GLOBAL_CONFIGURATION)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    if expected_step:
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == expected_step
    else:
        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
