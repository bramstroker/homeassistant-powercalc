from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import RegistryEntryWithDefaults, mock_registry

from custom_components.powercalc.const import (
    CONF_CUSTOM_MODEL_DIRECTORY,
    CONF_MANUFACTURER,
    CONF_MODEL,
)
from tests.common import assert_entity_state, get_test_profile_dir, mock_device, run_powercalc_setup, set_states


async def test_translation_key_standby_sub_profile(
    hass: HomeAssistant,
) -> None:
    """
    Regression for dual-light devices where only one sub-profile should contribute standby power.
    """
    device_id = "device-with-nightlight"
    mock_registry(
        hass,
        {
            "light.test": RegistryEntryWithDefaults(
                entity_id="light.test",
                unique_id="main",
                platform="test",
                device_id=device_id,
                translation_key="main",
            ),
            "light.test_nightlight": RegistryEntryWithDefaults(
                entity_id="light.test_nightlight",
                unique_id="nightlight",
                platform="test",
                device_id=device_id,
                translation_key="nightlight",
            ),
        },
    )
    mock_device(hass, device_id, "test", "translation_key_standby_sub_profile")

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_ENTITY_ID: "light.test",
                CONF_NAME: "Main",
                CONF_MANUFACTURER: "test",
                CONF_MODEL: "translation_key_standby_sub_profile",
                CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("translation_key_standby_sub_profile"),
            },
            {
                CONF_ENTITY_ID: "light.test_nightlight",
                CONF_NAME: "Nightlight",
                CONF_MANUFACTURER: "test",
                CONF_MODEL: "translation_key_standby_sub_profile",
                CONF_CUSTOM_MODEL_DIRECTORY: get_test_profile_dir("translation_key_standby_sub_profile"),
            },
        ],
    )

    await set_states(hass, [("light.test", STATE_OFF), ("light.test_nightlight", STATE_OFF)])
    assert_entity_state(hass, "sensor.main_power", "0.40")
    assert_entity_state(hass, "sensor.nightlight_power", "0.00")
    assert_entity_state(hass, "sensor.all_standby_power", "0.40")

    await set_states(hass, [("light.test_nightlight", STATE_ON)])
    assert_entity_state(hass, "sensor.main_power", "0.00")
    assert_entity_state(hass, "sensor.nightlight_power", "1.24")
    assert_entity_state(hass, "sensor.all_standby_power", "0.00")

    await set_states(hass, [("light.test_nightlight", STATE_OFF), ("light.test", STATE_ON)])
    assert_entity_state(hass, "sensor.main_power", "5.00")
    assert_entity_state(hass, "sensor.nightlight_power", "0.00")
    assert_entity_state(hass, "sensor.all_standby_power", "0.00")
