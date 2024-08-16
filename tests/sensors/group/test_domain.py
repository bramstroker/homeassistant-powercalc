from homeassistant.components.utility_meter.sensor import (
    SensorDeviceClass,
)
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import (
    mock_registry,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_EXCLUDE_ENTITIES,
    CONF_GROUP_TYPE,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_SENSOR_TYPE,
    GroupType,
    SensorType,
)
from tests.common import (
    setup_config_entry,
)


async def test_domain_group_all(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "sensor.a_power": RegistryEntry(
                entity_id="sensor.a_power",
                unique_id="1111",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.b_power": RegistryEntry(
                entity_id="sensor.b_power",
                unique_id="2222",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.c_power": RegistryEntry(
                entity_id="sensor.c_power",
                unique_id="3333",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.d_power": RegistryEntry(
                entity_id="sensor.c_power",
                unique_id="4444",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.a_energy": RegistryEntry(
                entity_id="sensor.a_energy",
                unique_id="5555",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
            ),
            "sensor.b_energy": RegistryEntry(
                entity_id="sensor.b_energy",
                unique_id="6666",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    await setup_config_entry(
        hass,
        {
            CONF_DOMAIN: "all",
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_GROUP_TYPE: GroupType.DOMAIN,
            CONF_NAME: "GroupAll",
            CONF_EXCLUDE_ENTITIES: ["sensor.d_power"],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    group_power_state = hass.states.get("sensor.groupall_power")
    assert group_power_state
    assert group_power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.a_power",
        "sensor.b_power",
        "sensor.c_power",
    }

    group_energy_state = hass.states.get("sensor.groupall_energy")
    assert group_energy_state
    assert group_energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.a_energy",
        "sensor.b_energy",
    }
