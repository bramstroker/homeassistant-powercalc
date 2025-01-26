import pytest
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry

from custom_components.powercalc import (
    CONF_CREATE_ENERGY_SENSORS,
    CONF_CREATE_UTILITY_METERS,
)
from custom_components.powercalc.common import (
    get_merged_sensor_configuration,
    get_wrapped_entity_name,
)
from custom_components.powercalc.const import CONF_CREATE_ENERGY_SENSOR


@pytest.mark.parametrize(
    "configs,output_config",
    [
        (
            [
                {
                    CONF_CREATE_UTILITY_METERS: True,
                    CONF_CREATE_ENERGY_SENSORS: False,
                },
                {
                    CONF_ENTITY_ID: "switch.test",
                    CONF_CREATE_UTILITY_METERS: False,
                },
            ],
            {
                CONF_ENTITY_ID: "switch.test",
                CONF_CREATE_ENERGY_SENSORS: False,
                CONF_CREATE_ENERGY_SENSOR: False,
                CONF_CREATE_UTILITY_METERS: False,
            },
        ),
        (
            [
                {
                    CONF_NAME: "foo",
                },
                {
                    CONF_ENTITY_ID: "switch.test",
                },
            ],
            {
                CONF_ENTITY_ID: "switch.test",
                CONF_CREATE_ENERGY_SENSOR: None,
            },
        ),
    ],
)
async def test_merge_configuration(
    configs: list[dict],
    output_config: dict,
) -> None:
    assert get_merged_sensor_configuration(*configs) == output_config


@pytest.mark.parametrize(
    "entity_id,entity_entry,device_entry,expected_name",
    [
        (
            "switch.my_switch",
            None,
            None,
            "my_switch",
        ),
        (
            "switch.my_switch",
            RegistryEntry(
                entity_id="switch.my_switch",
                unique_id="abc",
                platform="switch",
                name="My awesome switchy",
            ),
            None,
            "My awesome switchy",
        ),
        (
            "switch.my_switch",
            RegistryEntry(
                entity_id="switch.my_switch",
                unique_id="abc",
                platform="switch",
                has_entity_name=True,
                name=None,
            ),
            DeviceEntry(
                name="My awesome switchy",
            ),
            "My awesome switchy",
        ),
        (
            "switch.livingroom-smartplug-television",
            RegistryEntry(
                entity_id="switch.livingroom-smartplug-television",
                unique_id="abc",
                platform="switch",
                has_entity_name=True,
                name=None,
                original_name="Television",
            ),
            DeviceEntry(
                name="Livingroom-SmartPlug",
            ),
            "Livingroom-SmartPlug Television",
        ),
    ],
)
async def test_get_wrapped_entity_name(
    hass: HomeAssistant,
    entity_id: str,
    entity_entry: RegistryEntry | None,
    device_entry: DeviceEntry | None,
    expected_name: str,
) -> None:
    (__, object_id) = split_entity_id(entity_id)
    name = get_wrapped_entity_name(
        hass,
        entity_id,
        object_id,
        entity_entry,
        device_entry,
    )
    assert name == expected_name
