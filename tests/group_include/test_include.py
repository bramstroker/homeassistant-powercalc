import logging
import uuid

import pytest
from homeassistant.components import light
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_UNIQUE_ID,
    STATE_OFF,
)
from homeassistant.core import HomeAssistant
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
    CONF_TEMPLATE,
    DOMAIN,
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
                "entities": ["light.bathroom_mirror", "light.bathroom_spots"],
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
    hass: HomeAssistant, entity_reg: EntityRegistry, area_reg: AreaRegistry,
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


def _create_powercalc_config_entry(
    hass: HomeAssistant, source_entity_id: str,
) -> MockConfigEntry:
    unique_id = str(uuid.uuid4())
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: unique_id,
            CONF_ENTITY_ID: source_entity_id,
            CONF_FIXED: {CONF_POWER: 50},
        },
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)
    return entry
