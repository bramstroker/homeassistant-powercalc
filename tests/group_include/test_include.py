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
from homeassistant.helpers.entity_registry import EntityRegistry, RegistryEntry
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_AREA,
    CONF_CREATE_GROUP,
    CONF_FILTER,
    CONF_FIXED,
    CONF_GROUP,
    CONF_INCLUDE,
    CONF_POWER,
    CONF_SENSOR_TYPE,
    CONF_SUB_GROUPS,
    CONF_TEMPLATE,
    DOMAIN,
    ENTRY_DATA_ENERGY_ENTITY,
    ENTRY_DATA_POWER_ENTITY,
    SensorType,
)
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
    area_reg: AreaRegistry,
    area_input: str,
) -> None:
    await create_mock_light_entity(hass, create_discoverable_light("bathroom_mirror"))

    area = area_reg.async_get_or_create("Bathroom 1")
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
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture,
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

    await hass.async_start()
    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.lights_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.bathroom_spots_power",
        "sensor.kitchen_power",
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

    await hass.async_start()
    await hass.async_block_till_done()

    group_state = hass.states.get("sensor.powercalc_group_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {
        "sensor.tv_power",
        "sensor.soundbar_power",
    }


async def test_error_is_logged_when_group_not_exists(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture,
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

    _create_powercalc_config_entry(hass, "light.light_a")
    _create_powercalc_config_entry(hass, "light.light_e")
    _create_powercalc_config_entry(hass, "light.light_f")

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
    area_reg: AreaRegistry,
) -> None:
    area = area_reg.async_get_or_create("Bathroom 1")
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

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.test_light_power"}


async def test_include_yaml_configured_entity(
    hass: HomeAssistant,
    entity_reg: EntityRegistry,
    area_reg: AreaRegistry,
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

    area = area_reg.async_get_or_create("My area")
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
    area_reg: AreaRegistry,
) -> None:
    """Test that both powercalc and non powercalc entities can be included"""
    area = area_reg.async_get_or_create("bedroom")
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
    area_reg: AreaRegistry,
) -> None:
    """
    When one of the subgroups has no include entities resolved the other nested groups should just be setup
    """
    await create_mock_light_entity(hass, create_discoverable_light("bathroom_mirror"))

    area_bathroom = area_reg.async_get_or_create("Bathroom")
    area_reg.async_get_or_create("Bedroom")
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
    area_reg: AreaRegistry,
) -> None:
    await create_mock_light_entity(hass, create_discoverable_light("bathroom_mirror"))

    area_bathroom = area_reg.async_get_or_create("Bathroom")
    area_reg.async_get_or_create("Bedroom")
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
    area_reg: AreaRegistry,
) -> None:
    area = area_reg.async_get_or_create("Bathroom")
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
            },
        },
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(CONF_ENTITIES) == {"sensor.test"}


def _create_powercalc_config_entry(
    hass: HomeAssistant,
    source_entity_id: str,
) -> MockConfigEntry:
    __, object_id = split_entity_id(source_entity_id)

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
