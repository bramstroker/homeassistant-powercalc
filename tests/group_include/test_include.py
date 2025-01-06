import logging
import uuid

import pytest
from homeassistant.components import light
from homeassistant.components.group import DOMAIN as GROUP_DOMAIN
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_OFF,
)
from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import EntityRegistry, RegistryEntry, RegistryEntryDisabler
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc import CONF_CREATE_UTILITY_METERS
from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_ALL,
    CONF_AREA,
    CONF_CREATE_GROUP,
    CONF_FILTER,
    CONF_FIXED,
    CONF_GROUP,
    CONF_IGNORE_UNAVAILABLE_STATE,
    CONF_INCLUDE,
    CONF_INCLUDE_NON_POWERCALC_SENSORS,
    CONF_LABEL,
    CONF_OR,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    CONF_SUB_GROUPS,
    CONF_TEMPLATE,
    CONF_WILDCARD,
    DOMAIN,
    ENTRY_DATA_ENERGY_ENTITY,
    ENTRY_DATA_POWER_ENTITY,
    SensorType,
)
from custom_components.powercalc.group_include.include import find_entities
from custom_components.test.light import MockLight
from tests.common import (
    create_discoverable_light,
    create_mock_light_entity,
    get_simple_fixed_config,
    run_powercalc_setup,
)


@pytest.mark.parametrize(
    "area_input",
    [
        pytest.param("bathroom_1", id="by id"),
        pytest.param("Bathroom 1", id="by name"),
    ],
)
async def test_include_area(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
    area_registry: AreaRegistry,
    area_input: str,
) -> None:
    await create_mock_light_entity(hass, create_discoverable_light("bathroom_mirror"))

    area = area_registry.async_get_or_create("Bathroom 1")
    entity_reg.async_update_entity("light.bathroom_mirror", area_id=area.id)

    _create_powercalc_config_entry(hass, "light.bathroom_mirror")

    await run_powercalc_setup(
        hass,
        {CONF_CREATE_GROUP: "Test include", CONF_INCLUDE: {CONF_AREA: area_input}},
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.bathroom_mirror_power"}


async def test_include_area_not_found(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test area not found",
            CONF_INCLUDE: {CONF_AREA: "hallway"},
        },
    )
    assert "No area with id or name" in caplog.text


async def test_include_light_group(hass: HomeAssistant) -> None:
    discoverable_light = create_discoverable_light("bathroom_mirror")
    _create_powercalc_config_entry(hass, "light.bathroom_mirror")

    non_discoverable_light = MockLight("bathroom_spots")

    await create_mock_light_entity(hass, [discoverable_light, non_discoverable_light])

    # Ugly hack, maybe I can figure out something better in the future.
    # Light domain is already setup for platform test, remove the component so we can setup light group
    if light.DOMAIN in hass.config.components:
        hass.config.components.remove(light.DOMAIN)

    await async_setup_component(
        hass,
        light.DOMAIN,
        {
            light.DOMAIN: {
                "platform": "group",
                "name": "Bathroom",
                "entities": [
                    "light.bathroom_mirror",
                    "light.bathroom_spots",
                    "light.whatever",
                ],
            },
        },
    )
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include lightgroup",
            CONF_INCLUDE: {CONF_GROUP: "light.bathroom"},
        },
    )

    await hass.async_start()
    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.test_include_lightgroup_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.bathroom_mirror_power"}


async def test_error_is_logged_when_light_group_not_exists(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "Powercalc group",
                CONF_INCLUDE: {CONF_GROUP: "light.some_group"},
            },
        ],
    )
    assert "Light group light.some_group not found" in caplog.text


async def test_include_domain(hass: HomeAssistant) -> None:
    """Test domain include option, which includes all entities where the source entity matches a certain domain"""
    await create_mock_light_entity(
        hass,
        [
            create_discoverable_light("bathroom_spots", "1111"),
            create_discoverable_light("kitchen", "2222"),
        ],
    )

    _create_powercalc_config_entry(hass, "light.bathroom_spots")
    _create_powercalc_config_entry(hass, "light.kitchen")

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "Lights",
                CONF_INCLUDE: {CONF_DOMAIN: "light"},
            },
        ],
    )

    group_state = hass.states.get("sensor.lights_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.bathroom_spots_power",
        "sensor.kitchen_power",
    }


async def test_include_domain_list(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "switch.test": RegistryEntry(
                entity_id="switch.test",
                unique_id="1111",
                platform="switch",
            ),
            "light.test2": RegistryEntry(
                entity_id="light.test2",
                unique_id="2222",
                platform="light",
            ),
            "sensor.test3": RegistryEntry(
                entity_id="sensor.test3",
                unique_id="3333",
                platform="sensor",
            ),
        },
    )
    _create_powercalc_config_entry(hass, "switch.test")
    _create_powercalc_config_entry(hass, "light.test2")
    _create_powercalc_config_entry(hass, "sensor.test3")

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "mygroup",
                CONF_INCLUDE: {CONF_DOMAIN: ["switch", "light"]},
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    group_state = hass.states.get("sensor.mygroup_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test_power",
        "sensor.test2_power",
    }


async def test_include_template(hass: HomeAssistant) -> None:
    await create_mock_light_entity(
        hass,
        [
            create_discoverable_light("bathroom_spots", "1111"),
            create_discoverable_light("kitchen", "2222"),
        ],
    )

    _create_powercalc_config_entry(hass, "light.bathroom_spots")
    _create_powercalc_config_entry(hass, "light.kitchen")

    template = "{{ states|selectattr('entity_id', 'eq', 'light.bathroom_spots')|map(attribute='entity_id')|list}}"
    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "Lights",
                CONF_INCLUDE: {CONF_TEMPLATE: template},
            },
        ],
    )

    await hass.async_start()
    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.lights_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.bathroom_spots_power"}


async def test_include_group(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.tv", "on")

    mock_registry(
        hass,
        {
            "switch.tv": RegistryEntry(
                entity_id="switch.tv",
                unique_id="12345",
                platform="switch",
            ),
            "switch.soundbar": RegistryEntry(
                entity_id="switch.soundbar",
                unique_id="123456",
                platform="switch",
            ),
        },
    )

    await async_setup_component(
        hass,
        SWITCH_DOMAIN,
        {
            SWITCH_DOMAIN: {
                "platform": GROUP_DOMAIN,
                "entities": ["switch.tv", "switch.soundbar"],
                "name": "Multimedia Group",
                "unique_id": "unique_identifier",
                "all": "false",
            },
        },
    )

    await run_powercalc_setup(
        hass,
        [
            get_simple_fixed_config("switch.tv"),
            get_simple_fixed_config("switch.soundbar"),
            {
                CONF_CREATE_GROUP: "Powercalc group",
                CONF_INCLUDE: {CONF_GROUP: "switch.multimedia_group"},
            },
        ],
    )

    group_state = hass.states.get("sensor.powercalc_group_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.tv_power",
        "sensor.soundbar_power",
    }


async def test_include_skips_unsupported_entities(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    mock_device_registry(
        hass,
        {
            "device-a": DeviceEntry(
                id="device-a",
                manufacturer="Signify",
                model="LCT012",
            ),
            "device-b": DeviceEntry(
                id="device-b",
                manufacturer="Signify",
                model="Room",
            ),
        },
    )

    mock_registry(
        hass,
        {
            "light.a": RegistryEntry(
                entity_id="light.a",
                unique_id="111",
                platform="light",
                device_id="device-a",
            ),
            "light.b": RegistryEntry(
                entity_id="light.b",
                unique_id="222",
                platform="light",
                device_id="device-b",
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "Powercalc group",
                CONF_INCLUDE: {CONF_DOMAIN: "light"},
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    group_state = hass.states.get("sensor.powercalc_group_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.a_power",
    }

    assert len(caplog.records) == 0


async def test_error_is_logged_when_group_not_exists(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.ERROR)
    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "Powercalc group",
                CONF_INCLUDE: {CONF_GROUP: "switch.some_group"},
            },
        ],
    )
    assert "Group state switch.some_group not found" in caplog.text


async def test_combine_include_with_entities(hass: HomeAssistant) -> None:
    light_a = create_discoverable_light("light_a")
    light_b = MockLight("light_b")
    light_c = MockLight("light_c")
    light_d = MockLight("light_d")
    light_e = create_discoverable_light("light_e", "6765765756")
    light_f = create_discoverable_light("light_f", "676576575sds6")
    await create_mock_light_entity(
        hass,
        [light_a, light_b, light_c, light_d, light_e, light_f],
    )

    _create_powercalc_config_entry(hass, "light.light_a", light_a.unique_id)
    _create_powercalc_config_entry(hass, "light.light_e", light_e.unique_id)
    _create_powercalc_config_entry(hass, "light.light_f", light_f.unique_id)

    # Ugly hack, maybe I can figure out something better in the future.
    # Light domain is already setup for platform test, remove the component so we can setup light group
    if light.DOMAIN in hass.config.components:
        hass.config.components.remove(light.DOMAIN)

    await async_setup_component(
        hass,
        light.DOMAIN,
        {
            light.DOMAIN: [
                {
                    "platform": "group",
                    "name": "Light Group A",
                    "unique_id": "groupa",
                    "entities": ["light.light_a", "light.light_b"],
                },
                {
                    "platform": "group",
                    "name": "Light Group B",
                    "unique_id": "groupb",
                    "entities": [
                        "light.light_c",
                        "light.light_d",
                        "light.light_e",
                        "light.light_f",
                    ],
                },
                {
                    "platform": "group",
                    "name": "Light Group C",
                    "unique_id": "groupc",
                    "entities": ["light.light_group_a", "light.light_group_b"],
                },
            ],
        },
    )
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Powercalc Group",
            CONF_INCLUDE: {CONF_GROUP: "light.light_group_c"},
            CONF_ENTITIES: [
                get_simple_fixed_config("light.light_b", 50),
                get_simple_fixed_config("light.light_c", 50),
                {
                    CONF_CREATE_GROUP: "Subgroup A",
                    CONF_ENTITIES: [{CONF_ENTITY_ID: "light.light_e"}],
                },
                {
                    CONF_CREATE_GROUP: "Subgroup B",
                    CONF_ENTITIES: [{CONF_ENTITY_ID: "light.light_f"}],
                },
            ],
        },
    )

    group_state = hass.states.get("sensor.powercalc_group_power")
    assert group_state
    assert group_state.attributes.get("entities") == {
        "sensor.light_a_power",
        "sensor.light_b_power",
        "sensor.light_c_power",
        "sensor.light_e_power",
        "sensor.light_f_power",
    }


async def test_include_filter_domain(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
    area_registry: AreaRegistry,
) -> None:
    area = area_registry.async_get_or_create("Bathroom 1")
    await hass.async_block_till_done()

    mock_registry(
        hass,
        {
            "light.test_light": RegistryEntry(
                entity_id="light.test_light",
                unique_id="1111",
                platform="light",
                device_id="light-device-id",
                area_id=area.id,
            ),
            "switch.test_switch": RegistryEntry(
                entity_id="switch.test_switch",
                unique_id="2222",
                platform="switch",
                device_id="switch-device-id",
                area_id=area.id,
            ),
        },
    )

    mock_device_registry(
        hass,
        {
            "light-device-id": DeviceEntry(
                id="light-device-id",
                manufacturer="Signify",
                model="LCT012",
                area_id=area.id,
            ),
            "switch-device-id": DeviceEntry(
                id="switch-device-id",
                manufacturer="Shelly",
                model="Shelly Plug S",
                area_id=area.id,
            ),
        },
    )

    _create_powercalc_config_entry(hass, "light.test_light")
    _create_powercalc_config_entry(hass, "switch.test_switch")

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include",
            CONF_INCLUDE: {
                CONF_AREA: "bathroom_1",
                CONF_FILTER: {CONF_DOMAIN: "light"},
            },
        },
    )

    hass.states.async_set("light.test_light", STATE_OFF)
    await hass.async_block_till_done()
    await hass.async_block_till_done()  # Needed on 2024.4.3. Check if we can remove later

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.test_light_power"}


async def test_include_yaml_configured_entity(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
    area_registry: AreaRegistry,
) -> None:
    """Test that include also includes entities that the user configured with YAML"""

    light_a = MockLight("light_a")
    light_b = MockLight("light_b")
    light_c = create_discoverable_light("light_c")
    light_d = MockLight("light_d")
    await create_mock_light_entity(
        hass,
        [light_a, light_b, light_c, light_d],
    )

    area = area_registry.async_get_or_create("My area")
    entity_reg.async_update_entity(light_a.entity_id, area_id=area.id)
    entity_reg.async_update_entity(light_b.entity_id, area_id=area.id)
    entity_reg.async_update_entity(light_c.entity_id, area_id=area.id)

    _create_powercalc_config_entry(hass, light_a.entity_id)

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "Test include",
                CONF_INCLUDE: {
                    CONF_AREA: "my_area",
                },
            },
            {
                CONF_ENTITY_ID: light_b.entity_id,
                CONF_FIXED: {
                    CONF_POWER: 50,
                },
            },
            {
                CONF_ENTITY_ID: light_c.entity_id,
            },
        ],
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.light_a_power",
        "sensor.light_b_power",
        "sensor.light_c_power",
    }


async def test_include_non_powercalc_entities_in_group(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    """Test that both powercalc and non powercalc entities can be included"""
    area = area_registry.async_get_or_create("bedroom")
    await hass.async_block_till_done()

    _create_powercalc_config_entry(hass, "light.test")

    shelly_power_sensor = "sensor.shelly_power"
    shelly_energy_sensor = "sensor.shelly_energy"
    mock_registry(
        hass,
        {
            shelly_power_sensor: RegistryEntry(
                entity_id=shelly_power_sensor,
                unique_id="1111",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
                area_id=area.id,
            ),
            shelly_energy_sensor: RegistryEntry(
                entity_id=shelly_energy_sensor,
                unique_id="2222",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
                area_id=area.id,
            ),
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="3333",
                platform="light",
                area_id=area.id,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include",
            CONF_INCLUDE: {
                CONF_AREA: "bedroom",
            },
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    power_state = hass.states.get("sensor.test_include_power")
    assert power_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test_power",
        shelly_power_sensor,
    }

    energy_state = hass.states.get("sensor.test_include_energy")
    assert energy_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.test_energy",
        shelly_energy_sensor,
    }


async def test_group_setup_continues_when_subgroup_has_no_include_entities(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
    area_registry: AreaRegistry,
) -> None:
    """
    When one of the subgroups has no include entities resolved the other nested groups should just be setup
    """
    await create_mock_light_entity(hass, create_discoverable_light("bathroom_mirror"))

    area_bathroom = area_registry.async_get_or_create("Bathroom")
    area_registry.async_get_or_create("Bedroom")
    entity_reg.async_update_entity("light.bathroom_mirror", area_id=area_bathroom.id)

    _create_powercalc_config_entry(hass, "light.bathroom_mirror")

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "GroupA",
            CONF_ENTITIES: [
                {
                    CONF_CREATE_GROUP: "GroupB",
                    CONF_INCLUDE: {CONF_AREA: "bedroom"},
                },
                {
                    CONF_CREATE_GROUP: "GroupC",
                    CONF_INCLUDE: {CONF_AREA: "bathroom"},
                },
            ],
        },
    )

    assert hass.states.get("sensor.groupa_power")
    assert not hass.states.get("sensor.groupb_power")
    assert hass.states.get("sensor.groupc_power")


async def test_area_groups_as_subgroups(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
    area_registry: AreaRegistry,
) -> None:
    await create_mock_light_entity(hass, create_discoverable_light("bathroom_mirror"))

    area_bathroom = area_registry.async_get_or_create("Bathroom")
    area_registry.async_get_or_create("Bedroom")
    entity_reg.async_update_entity("light.bathroom_mirror", area_id=area_bathroom.id)

    _create_powercalc_config_entry(hass, "light.bathroom_mirror")

    group_a_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: "GroupA",
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_AREA: area_bathroom.name,
        },
        unique_id="groupA",
    )
    group_a_entry.add_to_hass(hass)

    group_b_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_NAME: "GroupB",
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_SUB_GROUPS: [group_a_entry.entry_id],
        },
        unique_id="groupB",
    )
    group_b_entry.add_to_hass(hass)

    await run_powercalc_setup(hass, {})

    group_a_power = hass.states.get("sensor.groupa_power")
    assert group_a_power
    assert group_a_power.attributes.get(CONF_ENTITIES) == {
        "sensor.bathroom_mirror_power",
    }

    group_b_power = hass.states.get("sensor.groupb_power")
    assert group_b_power
    assert group_b_power.attributes.get(CONF_ENTITIES) == {
        "sensor.bathroom_mirror_power",
    }


async def test_power_group_does_not_include_binary_sensors(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    area = area_registry.async_get_or_create("Bathroom")
    await hass.async_block_till_done()

    mock_registry(
        hass,
        {
            "binary_sensor.test": RegistryEntry(
                entity_id="binary_sensor.test",
                unique_id="1111",
                platform="binary_sensor",
                device_class=SensorDeviceClass.POWER,
                area_id=area.id,
            ),
            "sensor.test": RegistryEntry(
                entity_id="sensor.test",
                unique_id="2222",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
                area_id=area.id,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include",
            CONF_INCLUDE: {
                CONF_AREA: "bathroom",
                CONF_INCLUDE_NON_POWERCALC_SENSORS: True,
            },
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {"sensor.test"}


async def test_energy_group_does_not_include_utility_meters(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="1111",
                platform="light",
            ),
            "sensor.test": RegistryEntry(
                entity_id="sensor.test",
                unique_id="2222",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
            ),
            "sensor.test_daily": RegistryEntry(
                entity_id="sensor.test_daily",
                unique_id="3333",
                platform="utility_meter",
                device_class=SensorDeviceClass.ENERGY,
            ),
            "sensor.test_hourly": RegistryEntry(
                entity_id="sensor.test_hourly",
                unique_id="4444",
                platform="utility_meter",
                device_class=SensorDeviceClass.ENERGY,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_ENTITY_ID: "light.test",
                CONF_UNIQUE_ID: "5555",
                CONF_NAME: "Test powercalc",
                CONF_FIXED: {CONF_POWER: 50},
                CONF_CREATE_UTILITY_METERS: True,
            },
            {
                CONF_CREATE_GROUP: "Test include",
                CONF_INCLUDE: {
                    CONF_ALL: None,
                },
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    group_state = hass.states.get("sensor.test_include_energy")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {"sensor.test", "sensor.test_powercalc_energy"}


async def test_include_group_does_not_include_disabled_sensors(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "sensor.test_energy": RegistryEntry(
                entity_id="sensor.test_energy",
                unique_id="1111",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
            ),
            "sensor.test_disabled_energy": RegistryEntry(
                entity_id="sensor.test_disabled_energy",
                unique_id="2222",
                platform="sensor",
                device_class=SensorDeviceClass.ENERGY,
                disabled_by=RegistryEntryDisabler.USER,
            ),
            "sensor.test_power": RegistryEntry(
                entity_id="sensor.test_power",
                unique_id="3333",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
            "sensor.test_disabled_power": RegistryEntry(
                entity_id="sensor.test_disabled_power",
                unique_id="4444",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
                disabled_by=RegistryEntryDisabler.USER,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include",
            CONF_INCLUDE: {
                CONF_ALL: None,
            },
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {"sensor.test_power"}

    group_state = hass.states.get("sensor.test_include_energy")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {"sensor.test_energy"}


async def test_include_by_label(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "sensor.test": RegistryEntry(
                entity_id="sensor.test",
                unique_id="1111",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
                labels=["my_label"],
            ),
            "sensor.test2": RegistryEntry(
                entity_id="sensor.test",
                unique_id="2222",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
                labels=["other_label"],
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include",
            CONF_INCLUDE: {
                CONF_LABEL: "my_label",
            },
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {"sensor.test"}


async def test_include_by_wildcard(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "binary_sensor.test": RegistryEntry(
                entity_id="sensor.tv_power",
                unique_id="1111",
                platform="binary_sensor",
                device_class=SensorDeviceClass.POWER,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include",
            CONF_INCLUDE: {
                CONF_WILDCARD: "sensor.tv_*",
            },
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {"sensor.tv_power"}


async def test_include_by_wildcard_in_nested_groups(
    hass: HomeAssistant,
) -> None:
    light_a = create_discoverable_light("some_a", "111")
    light_b = create_discoverable_light("other_b", "222")
    light_c = create_discoverable_light("other_c", "333")
    await create_mock_light_entity(
        hass,
        [light_a, light_b, light_c],
    )

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include a",
            CONF_ENTITIES: [
                {
                    CONF_ENTITY_ID: "light.some_a",
                },
                {
                    CONF_CREATE_GROUP: "Test include b",
                    CONF_INCLUDE: {
                        CONF_WILDCARD: "light.other_*",
                    },
                },
            ],
            CONF_IGNORE_UNAVAILABLE_STATE: True,
        },
    )

    group_a_state = hass.states.get("sensor.test_include_a_power")
    assert group_a_state
    assert group_a_state.attributes.get(CONF_ENTITIES) == {
        "sensor.some_a_power",
        "sensor.other_b_power",
        "sensor.other_c_power",
    }

    group_b_state = hass.states.get("sensor.test_include_b_power")
    assert group_b_state
    assert group_b_state.attributes.get(CONF_ENTITIES) == {
        "sensor.other_b_power",
        "sensor.other_c_power",
    }


async def test_include_complex_nested_filters(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    area = area_registry.async_get_or_create("Living room")
    mock_registry(
        hass,
        {
            "switch.test": RegistryEntry(
                entity_id="binary_sensor.test",
                unique_id="1111",
                platform="binary_sensor",
            ),
            "switch.tv": RegistryEntry(
                entity_id="switch.tv",
                unique_id="2222",
                platform="switch",
                area_id=area.id,
            ),
            "light.tv_ambilights": RegistryEntry(
                entity_id="light.tv_ambilights",
                unique_id="3333",
                platform="light",
                area_id=area.id,
            ),
            "light.living_room": RegistryEntry(
                entity_id="light.living_room",
                unique_id="4444",
                platform="light",
                area_id=area.id,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            get_simple_fixed_config("switch.test"),
            get_simple_fixed_config("switch.tv"),
            get_simple_fixed_config("light.tv_ambilights"),
            get_simple_fixed_config("light.living_room"),
            {
                CONF_CREATE_GROUP: "Test include",
                CONF_INCLUDE: {
                    CONF_AREA: "Living room",
                    CONF_FILTER: {
                        CONF_OR: [
                            {CONF_DOMAIN: "switch"},
                            {CONF_WILDCARD: "*ambilights"},
                        ],
                    },
                },
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {
        "sensor.tv_power",
        "sensor.tv_ambilights_power",
    }


async def test_include_by_area_combined_with_domain_filter(hass: HomeAssistant, area_registry: AreaRegistry) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/1984"""
    area_kitchen = area_registry.async_get_or_create("kitchen")
    area_conservatory = area_registry.async_get_or_create("conservatory")
    mock_registry(
        hass,
        {
            "switch.kitchen_switch": RegistryEntry(
                entity_id="switch.kitchen_switch",
                unique_id="1111",
                platform="switch",
                area_id=area_kitchen.id,
            ),
            "switch.conservatory_switch": RegistryEntry(
                entity_id="switch.conservatory_switch",
                unique_id="2222",
                platform="switch",
                area_id=area_conservatory.id,
            ),
            "light.kitchen_light": RegistryEntry(
                entity_id="light.kitchen_light",
                unique_id="3333",
                platform="light",
                area_id=area_kitchen.id,
            ),
            "light.conservatory_light": RegistryEntry(
                entity_id="light.conservatory_light",
                unique_id="4444",
                platform="light",
                area_id=area_conservatory.id,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            get_simple_fixed_config("light.kitchen_light"),
            get_simple_fixed_config("light.conservatory_light"),
            {
                CONF_CREATE_GROUP: "Indoor lights",
                CONF_ENTITIES: [
                    {
                        CONF_CREATE_GROUP: "Conservatory",
                        CONF_INCLUDE: {
                            CONF_AREA: "conservatory",
                            CONF_FILTER: {
                                CONF_DOMAIN: "light",
                            },
                        },
                        CONF_IGNORE_UNAVAILABLE_STATE: True,
                    },
                    {
                        CONF_CREATE_GROUP: "Kitchen",
                        CONF_INCLUDE: {
                            CONF_AREA: "kitchen",
                            CONF_FILTER: {
                                CONF_DOMAIN: "light",
                            },
                        },
                        CONF_IGNORE_UNAVAILABLE_STATE: True,
                    },
                ],
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    group_state = hass.states.get("sensor.indoor_lights_power")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {
        "sensor.kitchen_light_power",
        "sensor.conservatory_light_power",
    }

    group_kitchen_state = hass.states.get("sensor.kitchen_power")
    assert group_kitchen_state
    assert group_kitchen_state.attributes.get(CONF_ENTITIES) == {
        "sensor.kitchen_light_power",
    }

    group_conservatory_state = hass.states.get("sensor.conservatory_power")
    assert group_conservatory_state
    assert group_conservatory_state.attributes.get(CONF_ENTITIES) == {
        "sensor.conservatory_light_power",
    }


async def test_include_all(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "switch.switch": RegistryEntry(
                entity_id="switch.switch",
                unique_id="1111",
                platform="switch",
            ),
            "light.light": RegistryEntry(
                entity_id="light.light",
                unique_id="2222",
                platform="light",
            ),
            "sensor.existing_power": RegistryEntry(
                entity_id="sensor.existing_power",
                unique_id="3333",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            get_simple_fixed_config("light.light"),
            get_simple_fixed_config("switch.switch"),
            {
                CONF_CREATE_GROUP: "All",
                CONF_INCLUDE: {
                    CONF_ALL: None,
                },
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    group_state = hass.states.get("sensor.all_power")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {
        "sensor.switch_power",
        "sensor.light_power",
        "sensor.existing_power",
    }


async def test_exclude_non_powercalc_sensors(hass: HomeAssistant) -> None:
    mock_registry(
        hass,
        {
            "switch.switch": RegistryEntry(
                entity_id="switch.switch",
                unique_id="1111",
                platform="switch",
            ),
            "sensor.existing_power": RegistryEntry(
                entity_id="sensor.existing_power",
                unique_id="3333",
                platform="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
        },
    )

    await run_powercalc_setup(
        hass,
        [
            get_simple_fixed_config("switch.switch"),
            {
                CONF_CREATE_GROUP: "All",
                CONF_INCLUDE: {
                    CONF_ALL: None,
                    CONF_INCLUDE_NON_POWERCALC_SENSORS: False,
                },
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    group_state = hass.states.get("sensor.all_power")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {
        "sensor.switch_power",
    }


async def test_include_logs_warning(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    """See github discussion #2008"""

    caplog.set_level(logging.WARNING)

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "All lights",
                CONF_ENTITIES: [
                    {
                        CONF_CREATE_GROUP: "Include group",
                        CONF_INCLUDE: {
                            CONF_WILDCARD: "light.some*",
                        },
                    },
                ],
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    error_messages = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(error_messages) == 0
    assert "Could not resolve any entities in group" in caplog.text


async def test_irrelevant_entity_domains_are_skipped(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    mock_device_registry(
        hass,
        {
            "device-a": DeviceEntry(
                id="device-a",
                manufacturer="Signify",
                model="LCT012",
            ),
        },
    )
    mock_registry(
        hass,
        {
            "light.test": RegistryEntry(
                entity_id="light.test",
                unique_id="2222",
                platform="hue",
                device_id="device-a",
            ),
            "scene.test": RegistryEntry(
                entity_id="scene.test",
                unique_id="3333",
                platform="hue",
                device_id="device-a",
            ),
            "event.test": RegistryEntry(
                entity_id="event.test",
                unique_id="4444",
                platform="hue",
                device_id="device-a",
            ),
        },
    )
    _, discoverable_entities = await find_entities(hass)
    assert len(discoverable_entities) == 1
    assert "light.test" in discoverable_entities

    assert "scene.test" not in caplog.text
    assert "event.test" not in caplog.text


def _create_powercalc_config_entry(
    hass: HomeAssistant,
    source_entity_id: str,
    unique_id: str | None = None,
) -> MockConfigEntry:
    __, object_id = split_entity_id(source_entity_id)

    if unique_id is None:
        unique_id = str(uuid.uuid4())
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_ENTITY_ID: source_entity_id,
            CONF_FIXED: {CONF_POWER: 50},
            ENTRY_DATA_POWER_ENTITY: f"sensor.{object_id}_power",
            ENTRY_DATA_ENERGY_ENTITY: f"sensor.{object_id}_energy",
        },
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)
    return entry
