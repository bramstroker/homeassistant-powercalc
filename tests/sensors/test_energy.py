from homeassistant.components.utility_meter.sensor import SensorDeviceClass
from homeassistant.const import CONF_ENTITIES, CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import (
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    ATTR_SOURCE_DOMAIN,
    ATTR_SOURCE_ENTITY,
    CONF_CREATE_GROUP,
    CONF_DISABLE_EXTENDED_ATTRIBUTES,
    CONF_ENERGY_SENSOR_ID,
    CONF_FIXED,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
)

from ..common import (
    create_input_boolean,
    get_simple_fixed_config,
    run_powercalc_setup_yaml_config,
)


async def test_related_energy_sensor_is_used_for_existing_power_sensor(
    hass: HomeAssistant,
):
    await create_input_boolean(hass)

    mock_device_registry(
        hass,
        {
            "shelly-device": DeviceEntry(
                id="shelly-device-id", manufacturer="Shelly", model="Plug S"
            )
        },
    )

    mock_registry(
        hass,
        {
            "sensor.existing_power": RegistryEntry(
                entity_id="sensor.existing_power",
                unique_id="1234",
                platform="sensor",
                device_id="shelly-device-id",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.existing_energy": RegistryEntry(
                entity_id="sensor.existing_energy",
                unique_id="12345",
                platform="sensor",
                device_id="shelly-device-id",
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "sensor.dummy",
                    CONF_POWER_SENSOR_ID: "sensor.existing_power",
                },
            ],
        },
    )

    await hass.async_block_till_done()

    power_state = hass.states.get("sensor.testgroup_power")
    assert power_state
    assert power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_power",
    }

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_energy",
    }


async def test_disable_extended_attributes(hass: HomeAssistant) -> None:
    await create_input_boolean(hass)

    await run_powercalc_setup_yaml_config(
        hass,
        get_simple_fixed_config("input_boolean.test"),
        {CONF_DISABLE_EXTENDED_ATTRIBUTES: True},
    )

    energy_state = hass.states.get("sensor.test_energy")
    assert ATTR_SOURCE_DOMAIN not in energy_state.attributes
    assert ATTR_SOURCE_ENTITY not in energy_state.attributes


async def test_real_energy_sensor(hass: HomeAssistant) -> None:
    """Test user can refer an existing real energy sensor to create utility meters for it or add to group with YAML"""

    mock_registry(
        hass,
        {
            "sensor.existing_energy": RegistryEntry(
                entity_id="sensor.existing_energy",
                unique_id="12345",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    await hass.async_block_till_done()

    await run_powercalc_setup_yaml_config(
        hass,
        {
            CONF_CREATE_GROUP: "TestGroup",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "sensor.dummy",
                    CONF_FIXED: {CONF_POWER: 50},
                    CONF_ENERGY_SENSOR_ID: "sensor.existing_energy",
                },
            ],
        },
    )

    await hass.async_block_till_done()

    energy_state = hass.states.get("sensor.testgroup_energy")
    assert energy_state
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.existing_energy",
    }
