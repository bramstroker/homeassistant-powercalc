from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_NAME,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_MEMBERS,
    ATTR_SOURCE_ENTITY,
    ATTR_SOURCE_GROUP,
    ATTR_STATE,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_FIXED,
    CONF_FORCE_CALCULATE_GROUP_ENERGY,
    CONF_GROUP_POWER_ENTITIES,
    CONF_GROUP_TRACKED_POWER_ENTITIES,
    CONF_GROUP_TYPE,
    CONF_MAIN_POWER_SENSOR,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    DOMAIN,
    SERVICE_CALIBRATE_ENERGY,
    SERVICE_DEBUG_GROUP,
    SERVICE_GET_GROUP_ENTITIES,
    GroupType,
    SensorType,
)
from tests.common import create_mock_config_entry, run_powercalc_setup, set_states


@pytest.mark.parametrize("source_domain", ["light", "switch", "custom"])
@pytest.mark.parametrize("disable_attributes", [False, True])
async def test_integrated_energy_group_actions(
    hass: HomeAssistant,
    source_domain: str,
    disable_attributes: bool,
) -> None:
    source = "switch.test" if source_domain == "custom" else f"{source_domain}.test"
    await set_states(hass, [(source, "on")])
    await run_powercalc_setup(hass, {CONF_ENTITY_ID: source, CONF_FIXED: {CONF_POWER: 50}})
    config = {
        CONF_SENSOR_TYPE: SensorType.GROUP,
        CONF_NAME: "TestGroup",
        CONF_DISABLE_EXTENDED_ATTRIBUTES: disable_attributes,
    }
    if source_domain == "custom":
        config.update({CONF_GROUP_POWER_ENTITIES: ["sensor.test_power"], CONF_FORCE_CALCULATE_GROUP_ENERGY: True})
    else:
        config.update({CONF_GROUP_TYPE: GroupType.DOMAIN, CONF_DOMAIN: source_domain})
    await create_mock_config_entry(hass, config)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CALIBRATE_ENERGY,
        {ATTR_ENTITY_ID: "sensor.testgroup_energy", "value": "1.25"},
        blocking=True,
    )

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_GROUP_ENTITIES,
        {ATTR_ENTITY_ID: "sensor.testgroup_energy"},
        blocking=True,
        return_response=True,
    )
    assert response["sensor.testgroup_energy"] == {
        ATTR_ENTITIES: {"sensor.test_power"},
        ATTR_SOURCE_ENTITY: "sensor.testgroup_power",
    }

    power_response = await hass.services.async_call(
        DOMAIN,
        SERVICE_DEBUG_GROUP,
        {ATTR_ENTITY_ID: "sensor.testgroup_power"},
        blocking=True,
        return_response=True,
    )
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_DEBUG_GROUP,
        {ATTR_ENTITY_ID: "sensor.testgroup_energy"},
        blocking=True,
        return_response=True,
    )
    assert response["sensor.testgroup_energy"] == {
        ATTR_STATE: "1.2500",
        ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR,
        ATTR_SOURCE_GROUP: {ATTR_ENTITY_ID: "sensor.testgroup_power", **power_response["sensor.testgroup_power"]},
    }
    assert response["sensor.testgroup_energy"][ATTR_SOURCE_GROUP][ATTR_MEMBERS] == {
        "sensor.test_power": {ATTR_STATE: "50.00", ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT},
    }


@pytest.mark.parametrize("action", [SERVICE_DEBUG_GROUP, SERVICE_GET_GROUP_ENTITIES])
@pytest.mark.parametrize("sensor_type", ["power", "energy"])
async def test_group_action_rejects_individual_sensor(hass: HomeAssistant, action: str, sensor_type: str) -> None:
    await set_states(hass, [("switch.test", "on")])
    await run_powercalc_setup(hass, {CONF_ENTITY_ID: "switch.test", CONF_FIXED: {CONF_POWER: 50}})

    with pytest.raises(ServiceValidationError, match=f"Entity sensor.test_{sensor_type}"):
        await hass.services.async_call(
            DOMAIN,
            action,
            {ATTR_ENTITY_ID: f"sensor.test_{sensor_type}"},
            blocking=True,
            return_response=True,
        )


@pytest.mark.parametrize("group_name", ["tracked", "untracked"])
async def test_tracked_energy_group_actions(hass: HomeAssistant, group_name: str) -> None:
    await set_states(
        hass,
        [
            ("sensor.main_power", "100", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}),
            ("sensor.test_power", "30", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}),
        ],
    )
    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_TYPE: GroupType.TRACKED_UNTRACKED,
            CONF_NAME: "Tracked / Untracked",
            CONF_MAIN_POWER_SENSOR: "sensor.main_power",
            CONF_GROUP_TRACKED_POWER_ENTITIES: ["sensor.test_power"],
        },
    )
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_DEBUG_GROUP,
        {ATTR_ENTITY_ID: f"sensor.{group_name}_energy"},
        blocking=True,
        return_response=True,
    )
    source_group = response[f"sensor.{group_name}_energy"][ATTR_SOURCE_GROUP]
    assert source_group[ATTR_ENTITY_ID] == f"sensor.{group_name}_power"
    assert source_group[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.WATT
    assert source_group[ATTR_STATE] == ("30.00" if group_name == "tracked" else "70.00")

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_GROUP_ENTITIES,
        {ATTR_ENTITY_ID: f"sensor.{group_name}_energy"},
        blocking=True,
        return_response=True,
    )
    assert response[f"sensor.{group_name}_energy"][ATTR_ENTITIES] == (
        {"sensor.test_power"} if group_name == "tracked" else {"sensor.main_power", "sensor.tracked_power"}
    )
