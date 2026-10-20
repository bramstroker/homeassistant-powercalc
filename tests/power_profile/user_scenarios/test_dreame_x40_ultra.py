from homeassistant.components.vacuum import VacuumActivity
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
import pytest

from custom_components.powercalc.const import CONF_MANUFACTURER, CONF_MODEL
from tests.common import assert_entity_state, mock_devices, mock_entities_in_registry, run_powercalc_setup, set_states


@pytest.mark.parametrize("select_status", ["disabled", "missing", "enabled"])
async def test_dreame_x40_uses_vacuum_settings_attributes(hass: HomeAssistant, select_status: str) -> None:
    """Load the production profile without requiring the two settings selects."""
    mock_devices(hass, {"robot": {"manufacturer": "Dreame", "model": "RLX63CE-2"}})
    entities = {
        "vacuum.robot": {},
        "sensor.robot_state": {"translation_key": "state"},
        "sensor.robot_charging": {"translation_key": "charging_status"},
        "sensor.robot_battery": {"device_class": "battery"},
    }
    if select_status != "missing":
        disabled_by = RegistryEntryDisabler.USER if select_status == "disabled" else None
        entities["select.robot_temperature"] = {"translation_key": "water_temperature", "disabled_by": disabled_by}
        entities["select.robot_drying"] = {"translation_key": "drying_time", "disabled_by": disabled_by}
    mock_entities_in_registry(
        hass,
        {
            entity_id: {"device_id": "robot", "platform": "dreame_vacuum", **attributes}
            for entity_id, attributes in entities.items()
        },
    )
    await set_states(
        hass,
        [
            ("vacuum.robot", VacuumActivity.DOCKED, {"water_temperature": "Hot", "drying_time": 3}),
            ("sensor.robot_state", "washing"),
            ("sensor.robot_charging", "not_charging"),
            ("sensor.robot_battery", "75"),
        ],
    )
    if select_status == "enabled":
        # Conflicting select values must not override the vacuum attributes.
        await set_states(hass, [("select.robot_temperature", "normal"), ("select.robot_drying", "4h")])

    await run_powercalc_setup(
        hass,
        {CONF_ENTITY_ID: "vacuum.robot", CONF_MANUFACTURER: "dreame", CONF_MODEL: "RLX63CE-2"},
    )
    assert_entity_state(hass, "sensor.robot_power", "110.30")

    for status in ["washing", "clean_add_water"]:
        await set_states(hass, [("sensor.robot_state", status)], block_count=2)
        for temperature, expected_power in [
            ("Warm", "109.20"),
            ("Mild", "104.20"),
            ("Normal", "26.90"),
            ("Hot", "110.30"),
        ]:
            # Only attributes change: the vacuum remains docked throughout.
            await set_states(
                hass,
                [("vacuum.robot", VacuumActivity.DOCKED, {"water_temperature": temperature, "drying_time": 3})],
                block_count=2,
            )
            assert_entity_state(hass, "sensor.robot_power", expected_power)

    await set_states(hass, [("sensor.robot_state", "drying")], block_count=2)
    assert_entity_state(hass, "sensor.robot_power", "74.10")
    for drying_time, expected_power in [(4, "72.00"), (2, "65.60"), ("3", "74.10")]:
        await set_states(
            hass,
            [("vacuum.robot", VacuumActivity.DOCKED, {"water_temperature": "Hot", "drying_time": drying_time})],
            block_count=2,
        )
        assert_entity_state(hass, "sensor.robot_power", expected_power)

    # Missing or invalid settings retain the profile's existing default branch.
    for attributes in [{}, {"water_temperature": None, "drying_time": "unknown"}]:
        await set_states(hass, [("vacuum.robot", VacuumActivity.DOCKED, attributes)], block_count=2)
        assert_entity_state(hass, "sensor.robot_power", "5.47")
        await set_states(hass, [("sensor.robot_state", "washing")], block_count=2)
        assert_entity_state(hass, "sensor.robot_power", "5.47")
        await set_states(hass, [("sensor.robot_state", "drying")], block_count=2)

    await set_states(hass, [("sensor.robot_state", "charging"), ("sensor.robot_charging", "charging")], block_count=2)
    assert_entity_state(hass, "sensor.robot_power", "23.44")
