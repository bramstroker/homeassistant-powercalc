from homeassistant.components.utility_meter.sensor import (
    SensorDeviceClass,
)
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant

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
    assert_entity_state,
    create_mock_config_entry,
    mock_entities_in_registry,
)


async def test_domain_group_all(hass: HomeAssistant) -> None:
    mock_entities_in_registry(
        hass,
        {
            "sensor.a_power": {"device_class": SensorDeviceClass.POWER},
            "sensor.b_power": {"device_class": SensorDeviceClass.POWER},
            "sensor.c_power": {"device_class": SensorDeviceClass.POWER},
            "sensor.d_power": {"device_class": SensorDeviceClass.POWER},
            "sensor.a_energy": {"device_class": SensorDeviceClass.ENERGY},
            "sensor.b_energy": {"device_class": SensorDeviceClass.ENERGY},
        },
    )

    await create_mock_config_entry(
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

    assert_entity_state(
        hass,
        "sensor.groupall_power",
        attributes={
            ATTR_ENTITIES: {
                "sensor.a_power",
                "sensor.b_power",
                "sensor.c_power",
            },
        },
    )

    assert_entity_state(
        hass,
        "sensor.groupall_energy",
        attributes={
            ATTR_ENTITIES: {
                "sensor.a_energy",
                "sensor.b_energy",
            },
        },
    )
