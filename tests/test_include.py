import logging

import pytest
from homeassistant.components import light
from homeassistant.const import CONF_DOMAIN, CONF_ENTITIES
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.setup import async_setup_component

from custom_components.powercalc.const import (
    ATTR_ENTITIES,
    CONF_AREA,
    CONF_CREATE_GROUP,
    CONF_GROUP,
    CONF_INCLUDE,
    CONF_TEMPLATE,
)
from custom_components.test.light import MockLight

from .common import (
    create_discoverable_light,
    create_mock_light_entity,
    get_simple_fixed_config,
    run_powercalc_setup,
)


async def test_include_area(
    hass: HomeAssistant, entity_reg: EntityRegistry, area_reg: AreaRegistry
):
    await create_mock_light_entity(hass, create_discoverable_light("bathroom_mirror"))

    area = area_reg.async_get_or_create("Bathroom 1")
    await hass.async_block_till_done()
    entity_reg.async_update_entity("light.bathroom_mirror", area_id=area.id)
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {CONF_CREATE_GROUP: "Test include", CONF_INCLUDE: {CONF_AREA: "bathroom_1"}},
    )

    group_state = hass.states.get("sensor.test_include_power")
    assert group_state
    assert group_state.attributes.get(ATTR_ENTITIES) == {"sensor.bathroom_mirror_power"}

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include area by name",
            CONF_INCLUDE: {CONF_AREA: "Bathroom 1"},
        },
    )

    assert hass.states.get("sensor.test_include_area_by_name_power")


async def test_include_area_not_found(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
):
    caplog.set_level(logging.ERROR)
    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test area not found",
            CONF_INCLUDE: {CONF_AREA: "hallway"},
        },
    )
    assert "No area with id or name" in caplog.text


async def test_include_light_group(hass: HomeAssistant):
    discoverable_light = create_discoverable_light("bathroom_mirror")
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
            }
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
    await create_mock_light_entity(hass, [light_a, light_b, light_c, light_d])

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
                    "entities": ["light.light_c", "light.light_d"],
                },
                {
                    "platform": "group",
                    "name": "Light Group C",
                    "unique_id": "groupc",
                    "entities": ["light.light_group_a", "light.light_group_b"],
                },
            ]
        },
    )
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Powercalc Group",
            CONF_ENTITIES: [
                get_simple_fixed_config("light.light_b", 50),
                get_simple_fixed_config("light.light_c", 50),
            ],
            CONF_INCLUDE: {CONF_GROUP: "light.light_group_c"},
        },
    )

    group_state = hass.states.get("sensor.powercalc_group_power")
    assert group_state
    assert group_state.attributes.get("entities") == {
        "sensor.light_a_power",
        "sensor.light_b_power",
        "sensor.light_c_power",
    }
