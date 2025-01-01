import logging

import pytest
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.powercalc.const import CONF_CUSTOM_MODEL_DIRECTORY, CONF_MANUFACTURER, CONF_MODEL, CONF_VARIABLES, DUMMY_ENTITY_ID
from custom_components.powercalc.power_profile.error import LibraryError
from custom_components.powercalc.power_profile.library import ProfileLibrary
from tests.common import get_test_config_dir, get_test_profile_dir, run_powercalc_setup


async def test_custom_field_variables_from_yaml_config(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test custom field variables can be passed from YAML configuration"""
    caplog.set_level(logging.ERROR)
    hass.config.config_dir = get_test_config_dir()

    hass.states.async_set("sensor.test", STATE_ON)
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "custom_fields",
            CONF_VARIABLES: {
                "some_entity": "sensor.test",
            },
        },
    )

    assert not caplog.records

    assert hass.states.get("sensor.test_power").state == "20.00"


async def test_validation_fails_when_not_all_variables_passed(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """Test error is logged when not all variables are passed, when setting up profile with custom fields"""
    caplog.set_level(logging.ERROR)
    hass.config.config_dir = get_test_config_dir()

    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: DUMMY_ENTITY_ID,
            CONF_NAME: "Test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "custom_fields",
            CONF_VARIABLES: {},
        },
    )

    assert "Missing variables for fields: some_entity" in caplog.text


@pytest.mark.parametrize(
    "custom_field_keys,variables,valid",
    [
        (["var1"], {"var1": "sensor.foo"}, True),
        ([], {}, True),
        (["var1", "var2"], {"var1": "sensor.test"}, False),
        (["var1"], {"var3": "sensor.test"}, False),
        (["var1"], {"var1": "sensor.test", "var2": "sensor.test"}, False),
    ],
)
async def test_validate_variables(
    hass: HomeAssistant,
    custom_field_keys: list,
    variables: dict,
    valid: bool,
) -> None:
    lib = await ProfileLibrary.factory(hass)

    custom_fields = {key: {"name": "test", "selector": {"number": {}}} for key in custom_field_keys}
    json_data = {"fields": custom_fields}

    if not valid:
        with pytest.raises(LibraryError):
            lib.validate_variables(
                json_data,
                variables,
            )
        return

    lib.validate_variables(
        json_data,
        variables,
    )


async def test_custom_fields_with_template(hass: HomeAssistant) -> None:
    """Test custom field variables can be passed from YAML configuration"""
    hass.states.async_set("switch.test", STATE_ON)
    await hass.async_block_till_done()
    await run_powercalc_setup(
        hass,
        {
            CONF_ENTITY_ID: "switch.test",
            CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("custom_fields_template"),
            CONF_VARIABLES: {
                "num_switches": 4,
            },
        },
    )

    assert hass.states.get("sensor.test_power").state == "0.80"
