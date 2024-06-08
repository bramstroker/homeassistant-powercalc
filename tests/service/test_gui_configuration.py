import uuid

import pytest
from homeassistant.const import CONF_ENTITY_ID, CONF_MODE, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.typing import ConfigType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc import CONF_FIXED, CONF_SENSOR_TYPE, DOMAIN, SensorType
from custom_components.powercalc.const import (
    CONF_ENERGY_INTEGRATION_METHOD,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_POWER,
    ENERGY_INTEGRATION_METHOD_LEFT,
    ENERGY_INTEGRATION_METHOD_RIGHT,
    ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
    SERVICE_CHANGE_GUI_CONFIGURATION,
    CalculationStrategy,
)
from tests.common import run_powercalc_setup


async def test_change_gui_configuration(hass: HomeAssistant) -> None:
    config_entry_a = create_config_entry(
        "light.a",
        {
            CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_RIGHT,
            CONF_IGNORE_UNAVAILABLE_STATE: False,
        },
    )
    config_entry_a.add_to_hass(hass)

    config_entry_b = create_config_entry(
        "light.b",
        {
            CONF_ENERGY_INTEGRATION_METHOD: ENERGY_INTEGRATION_METHOD_TRAPEZODIAL,
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )
    config_entry_b.add_to_hass(hass)

    config_entry_c = create_config_entry("light.c", {})
    config_entry_c.add_to_hass(hass)

    await run_powercalc_setup(hass, {}, {})

    await call_service(hass, CONF_IGNORE_UNAVAILABLE_STATE, "1")
    await call_service(
        hass,
        CONF_ENERGY_INTEGRATION_METHOD,
        ENERGY_INTEGRATION_METHOD_LEFT,
    )

    config_entry_a = hass.config_entries.async_get_entry(config_entry_a.entry_id)
    assert config_entry_a.data[CONF_IGNORE_UNAVAILABLE_STATE]
    assert config_entry_a.data[CONF_ENERGY_INTEGRATION_METHOD] == ENERGY_INTEGRATION_METHOD_LEFT

    config_entry_b = hass.config_entries.async_get_entry(config_entry_b.entry_id)
    assert config_entry_b.data[CONF_IGNORE_UNAVAILABLE_STATE]
    assert config_entry_b.data[CONF_ENERGY_INTEGRATION_METHOD] == ENERGY_INTEGRATION_METHOD_LEFT

    config_entry_c = hass.config_entries.async_get_entry(config_entry_c.entry_id)
    assert CONF_IGNORE_UNAVAILABLE_STATE not in config_entry_c.data


async def test_error_on_invalid_integration_method(hass: HomeAssistant) -> None:
    await run_powercalc_setup(hass, {}, {})

    with pytest.raises(HomeAssistantError):
        await call_service(hass, CONF_ENERGY_INTEGRATION_METHOD, "foo")


async def call_service(hass: HomeAssistant, field: str, value: str) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CHANGE_GUI_CONFIGURATION,
        {
            "field": field,
            "value": value,
        },
        blocking=True,
    )
    await hass.async_block_till_done()


def create_config_entry(
    entity_id: str,
    extra_entry_data: ConfigType,
) -> MockConfigEntry:
    unique_id = str(uuid.uuid4())
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_ENTITY_ID: entity_id,
            CONF_MODE: CalculationStrategy.FIXED,
            CONF_FIXED: {CONF_POWER: 50},
            **extra_entry_data,
        },
        title=f"Entry {entity_id}",
    )
