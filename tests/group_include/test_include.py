import logging

from homeassistant.components import light
from homeassistant.components.group import DOMAIN as GROUP_DOMAIN
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_MODE, ATTR_SUPPORTED_COLOR_MODES, ColorMode
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    CONF_DOMAIN,
    CONF_ENTITIES,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_UNIQUE_ID,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
from homeassistant.helpers.label_registry import LabelRegistry
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.powercalc import CONF_CREATE_UTILITY_METERS
from custom_components.powercalc.common import create_source_entity
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
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_NOT,
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
from tests.common import (
    assert_entity_state,
    create_mock_config_entry,
    get_simple_fixed_config,
    mock_device,
    mock_device_with_entities,
    mock_devices,
    mock_entities_in_registry,
    run_powercalc_setup,
    set_states,
)
from tests.config_flow.common import initialize_discovery_flow

# State attributes a lidl HG06462A light reports; needed for the LUT profile to match on discovery.
DISCOVERABLE_LIGHT_ATTRIBUTES = {
    ATTR_SUPPORTED_COLOR_MODES: [ColorMode.BRIGHTNESS],
    ATTR_COLOR_MODE: ColorMode.BRIGHTNESS,
    ATTR_BRIGHTNESS: 125,
}


@pytest.mark.parametrize(
    "area_input",
    [
        pytest.param("bathroom_1", id="by id"),
        pytest.param("Bathroom 1", id="by name"),
    ],
)
async def test_include_area(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
    area_input: str,
) -> None:
    area = area_registry.async_get_or_create("Bathroom 1")
    mock_device_with_entities(hass, "light.bathroom_mirror", "lidl", "HG06462A", area_id=area.id)
    await set_states(hass, [("light.bathroom_mirror", STATE_ON)])

    await _create_powercalc_config_entry(hass, "light.bathroom_mirror")

    await run_powercalc_setup(
        hass,
        {CONF_CREATE_GROUP: "Test include", CONF_INCLUDE: {CONF_AREA: area_input}},
    )

    assert_entity_state(hass, "sensor.test_include_power", attributes={ATTR_ENTITIES: {"sensor.bathroom_mirror_power"}})


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
    await _create_powercalc_config_entry(hass, "light.bathroom_mirror")

    mock_devices(hass, {"bathroom_mirror-device": {"manufacturer": "lidl", "model": "HG06462A"}})
    mock_entities_in_registry(
        hass,
        {"light.bathroom_mirror": {"device_id": "bathroom_mirror-device"}, "light.bathroom_spots": {}},
    )
    await set_states(hass, [("light.bathroom_mirror", STATE_ON), ("light.bathroom_spots", STATE_ON)])

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

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test include lightgroup",
            CONF_INCLUDE: {CONF_GROUP: "light.bathroom"},
        },
    )

    await hass.async_start()

    assert_entity_state(
        hass,
        "sensor.test_include_lightgroup_power",
        attributes={ATTR_ENTITIES: {"sensor.bathroom_mirror_power"}},
    )


async def test_include_deeply_nested_light_group(hass: HomeAssistant) -> None:
    """Light groups nested several levels deep should still resolve to the underlying light entities."""
    await _create_powercalc_config_entry(hass, "light.deep_light")

    mock_entities_in_registry(hass, {"light.deep_light": {}})
    await set_states(hass, [("light.deep_light", STATE_ON)])

    await async_setup_component(
        hass,
        light.DOMAIN,
        {
            light.DOMAIN: [
                {
                    "platform": "group",
                    "name": "Level 1",
                    "unique_id": "level1",
                    "entities": ["light.deep_light"],
                },
                {
                    "platform": "group",
                    "name": "Level 2",
                    "unique_id": "level2",
                    "entities": ["light.level_1"],
                },
                {
                    "platform": "group",
                    "name": "Level 3",
                    "unique_id": "level3",
                    "entities": ["light.level_2"],
                },
            ],
        },
    )
    await hass.async_block_till_done()

    await run_powercalc_setup(
        hass,
        {
            CONF_CREATE_GROUP: "Test deeply nested lightgroup",
            CONF_INCLUDE: {CONF_GROUP: "light.level_3"},
        },
    )

    await hass.async_start()

    assert_entity_state(
        hass,
        "sensor.test_deeply_nested_lightgroup_power",
        attributes={ATTR_ENTITIES: {"sensor.deep_light_power"}},
    )


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
    mock_devices(
        hass,
        {
            "bathroom_spots-device": {"manufacturer": "lidl", "model": "HG06462A"},
            "kitchen-device": {"manufacturer": "lidl", "model": "HG06462A"},
        },
    )
    mock_entities_in_registry(
        hass,
        {
            "light.bathroom_spots": {"unique_id": "1111", "device_id": "bathroom_spots-device"},
            "light.kitchen": {"unique_id": "2222", "device_id": "kitchen-device"},
        },
    )
    await set_states(hass, [("light.bathroom_spots", STATE_ON), ("light.kitchen", STATE_ON)])

    await _create_powercalc_config_entry(hass, "light.bathroom_spots")
    await _create_powercalc_config_entry(hass, "light.kitchen")

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "Lights",
                CONF_INCLUDE: {CONF_DOMAIN: "light"},
            },
        ],
    )

    assert_entity_state(
        hass,
        "sensor.lights_power",
        attributes={
            ATTR_ENTITIES: {
                "sensor.bathroom_spots_power",
                "sensor.kitchen_power",
            },
        },
    )


async def test_include_domain_list(hass: HomeAssistant) -> None:
    mock_entities_in_registry(
        hass,
        {
            "switch.test": {},
            "light.test2": {},
            "sensor.test3": {},
        },
    )
    await _create_powercalc_config_entry(hass, "switch.test")
    await _create_powercalc_config_entry(hass, "light.test2")
    await _create_powercalc_config_entry(hass, "sensor.test3")

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

    assert_entity_state(
        hass,
        "sensor.mygroup_power",
        attributes={
            ATTR_ENTITIES: {
                "sensor.test_power",
                "sensor.test2_power",
            },
        },
    )


async def test_include_template(hass: HomeAssistant) -> None:
    mock_devices(
        hass,
        {
            "bathroom_spots-device": {"manufacturer": "lidl", "model": "HG06462A"},
            "kitchen-device": {"manufacturer": "lidl", "model": "HG06462A"},
        },
    )
    mock_entities_in_registry(
        hass,
        {
            "light.bathroom_spots": {"unique_id": "1111", "device_id": "bathroom_spots-device"},
            "light.kitchen": {"unique_id": "2222", "device_id": "kitchen-device"},
        },
    )
    await set_states(hass, [("light.bathroom_spots", STATE_ON), ("light.kitchen", STATE_ON)])

    await _create_powercalc_config_entry(hass, "light.bathroom_spots")
    await _create_powercalc_config_entry(hass, "light.kitchen")

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

    assert_entity_state(hass, "sensor.lights_power", attributes={ATTR_ENTITIES: {"sensor.bathroom_spots_power"}})


async def test_include_group(hass: HomeAssistant) -> None:
    await set_states(hass, [("switch.tv", STATE_ON)])
    mock_entities_in_registry(
        hass,
        {
            "switch.tv": {},
            "switch.soundbar": {},
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

    assert_entity_state(
        hass,
        "sensor.powercalc_group_power",
        attributes={
            ATTR_ENTITIES: {
                "sensor.tv_power",
                "sensor.soundbar_power",
            },
        },
    )


async def test_include_skips_unsupported_entities(hass: HomeAssistant, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR)
    mock_devices(
        hass,
        {
            "device-a": {"manufacturer": "signify", "model": "LCT012"},
            "device-b": {"manufacturer": "signify", "model": "Room"},
        },
    )

    mock_entities_in_registry(
        hass,
        {
            "light.a": {"device_id": "device-a"},
            "light.b": {"device_id": "device-b"},
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

    assert_entity_state(
        hass,
        "sensor.powercalc_group_power",
        attributes={
            ATTR_ENTITIES: {
                "sensor.a_power",
            },
        },
    )

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
    mock_devices(
        hass,
        {
            "light_a-device": {"manufacturer": "lidl", "model": "HG06462A"},
            "light_e-device": {"manufacturer": "lidl", "model": "HG06462A"},
            "light_f-device": {"manufacturer": "lidl", "model": "HG06462A"},
        },
    )
    mock_entities_in_registry(
        hass,
        {
            "light.light_a": {"device_id": "light_a-device"},
            "light.light_b": {},
            "light.light_c": {},
            "light.light_d": {},
            "light.light_e": {"unique_id": "6765765756", "device_id": "light_e-device"},
            "light.light_f": {"unique_id": "676576575sds6", "device_id": "light_f-device"},
        },
    )
    await set_states(
        hass,
        [
            ("light.light_a", STATE_ON),
            ("light.light_b", STATE_ON),
            ("light.light_c", STATE_ON),
            ("light.light_d", STATE_ON),
            ("light.light_e", STATE_ON),
            ("light.light_f", STATE_ON),
        ],
    )

    await _create_powercalc_config_entry(hass, "light.light_a", "light.light_a")
    await _create_powercalc_config_entry(hass, "light.light_e", "6765765756")
    await _create_powercalc_config_entry(hass, "light.light_f", "676576575sds6")

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

    assert_entity_state(
        hass,
        "sensor.powercalc_group_power",
        attributes={
            "entities": {
                "sensor.light_a_power",
                "sensor.light_b_power",
                "sensor.light_c_power",
                "sensor.light_e_power",
                "sensor.light_f_power",
            },
        },
    )


async def test_include_filter_domain(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    area = area_registry.async_get_or_create("Bathroom 1")
    await hass.async_block_till_done()

    mock_entities_in_registry(
        hass,
        {
            "light.test_light": {"device_id": "light-device-id", "area_id": area.id},
            "switch.test_switch": {"device_id": "switch-device-id", "area_id": area.id},
        },
    )

    mock_devices(
        hass,
        {
            "light-device-id": {"manufacturer": "Signify", "model": "LCT012", "area_id": area.id},
            "switch-device-id": {"manufacturer": "Shelly", "model": "Shelly Plug S", "area_id": area.id},
        },
    )

    await _create_powercalc_config_entry(hass, "light.test_light")
    await _create_powercalc_config_entry(hass, "switch.test_switch")

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

    await set_states(hass, [("light.test_light", STATE_OFF)], block_count=2)
    assert_entity_state(hass, "sensor.test_include_power", attributes={ATTR_ENTITIES: {"sensor.test_light_power"}})


async def test_include_yaml_configured_entity(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    """Test that include also includes entities that the user configured with YAML"""

    area = area_registry.async_get_or_create("My area")
    mock_devices(hass, {"light_c-device": {"manufacturer": "lidl", "model": "HG06462A"}})
    mock_entities_in_registry(
        hass,
        {
            "light.light_a": {"area_id": area.id},
            "light.light_b": {"area_id": area.id},
            "light.light_c": {"device_id": "light_c-device", "area_id": area.id},
            "light.light_d": {},
        },
    )
    await set_states(
        hass,
        [
            ("light.light_a", STATE_ON),
            ("light.light_b", STATE_ON),
            ("light.light_c", STATE_ON),
            ("light.light_d", STATE_ON),
        ],
    )

    await _create_powercalc_config_entry(hass, "light.light_a")

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
                CONF_ENTITY_ID: "light.light_b",
                CONF_FIXED: {
                    CONF_POWER: 50,
                },
            },
            {
                CONF_ENTITY_ID: "light.light_c",
            },
        ],
    )

    assert_entity_state(
        hass,
        "sensor.test_include_power",
        attributes={
            ATTR_ENTITIES: {
                "sensor.light_a_power",
                "sensor.light_b_power",
                "sensor.light_c_power",
            },
        },
    )


async def test_include_non_powercalc_entities_in_group(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    """Test that both powercalc and non powercalc entities can be included"""
    area = area_registry.async_get_or_create("bedroom")
    await hass.async_block_till_done()

    await _create_powercalc_config_entry(hass, "light.test")

    shelly_power_sensor = "sensor.shelly_power"
    shelly_energy_sensor = "sensor.shelly_energy"
    mock_entities_in_registry(
        hass,
        {
            shelly_power_sensor: {"platform": "sensor", "device_class": SensorDeviceClass.POWER, "area_id": area.id},
            shelly_energy_sensor: {"platform": "sensor", "device_class": SensorDeviceClass.ENERGY, "area_id": area.id},
            "light.test": {"area_id": area.id},
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

    assert_entity_state(
        hass,
        "sensor.test_include_power",
        attributes={
            ATTR_ENTITIES: {
                "sensor.test_power",
                shelly_power_sensor,
            },
        },
    )

    assert_entity_state(
        hass,
        "sensor.test_include_energy",
        attributes={
            ATTR_ENTITIES: {
                "sensor.test_energy",
                shelly_energy_sensor,
            },
        },
    )


async def test_group_setup_continues_when_subgroup_has_no_include_entities(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    """
    When one of the subgroups has no include entities resolved the other nested groups should just be setup
    """
    area_bathroom = area_registry.async_get_or_create("Bathroom")
    area_registry.async_get_or_create("Bedroom")
    mock_device_with_entities(hass, "light.bathroom_mirror", "lidl", "HG06462A", area_id=area_bathroom.id)
    await set_states(hass, [("light.bathroom_mirror", STATE_ON)])

    await _create_powercalc_config_entry(hass, "light.bathroom_mirror")

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
    area_registry: AreaRegistry,
) -> None:
    area_bathroom = area_registry.async_get_or_create("Bathroom")
    area_registry.async_get_or_create("Bedroom")
    mock_device_with_entities(hass, "light.bathroom_mirror", "lidl", "HG06462A", area_id=area_bathroom.id)
    await set_states(hass, [("light.bathroom_mirror", STATE_ON)])

    await _create_powercalc_config_entry(hass, "light.bathroom_mirror")

    group_a_entry = await create_mock_config_entry(
        hass,
        {
            CONF_NAME: "GroupA",
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_AREA: area_bathroom.name,
        },
        setup=False,
    )

    await create_mock_config_entry(
        hass,
        {
            CONF_NAME: "GroupB",
            CONF_SENSOR_TYPE: SensorType.GROUP,
            CONF_SUB_GROUPS: [group_a_entry.entry_id],
        },
        setup=False,
    )

    await run_powercalc_setup(hass)

    assert_entity_state(
        hass,
        "sensor.groupa_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.bathroom_mirror_power",
            },
        },
    )

    assert_entity_state(
        hass,
        "sensor.groupb_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.bathroom_mirror_power",
            },
        },
    )


async def test_power_group_does_not_include_binary_sensors(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    area = area_registry.async_get_or_create("Bathroom")
    await hass.async_block_till_done()

    mock_entities_in_registry(
        hass,
        {
            "binary_sensor.test": {"device_class": SensorDeviceClass.POWER, "area_id": area.id},
            "sensor.test": {"device_class": SensorDeviceClass.POWER, "area_id": area.id},
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

    assert_entity_state(hass, "sensor.test_include_power", attributes={CONF_ENTITIES: {"sensor.test"}})


async def test_energy_group_does_not_include_utility_meters(hass: HomeAssistant) -> None:
    mock_entities_in_registry(
        hass,
        {
            "light.test": {},
            "sensor.test": {"device_class": SensorDeviceClass.ENERGY},
            "sensor.test_daily": {"platform": "utility_meter", "device_class": SensorDeviceClass.ENERGY},
            "sensor.test_hourly": {"platform": "utility_meter", "device_class": SensorDeviceClass.ENERGY},
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

    assert_entity_state(
        hass,
        "sensor.test_include_energy",
        attributes={CONF_ENTITIES: {"sensor.test", "sensor.test_powercalc_energy"}},
    )


async def test_include_group_does_not_include_disabled_sensors(hass: HomeAssistant) -> None:
    mock_entities_in_registry(
        hass,
        {
            "sensor.test_energy": {"device_class": SensorDeviceClass.ENERGY},
            "sensor.test_disabled_energy": {
                "device_class": SensorDeviceClass.ENERGY,
                "disabled_by": RegistryEntryDisabler.USER,
            },
            "sensor.test_power": {"device_class": SensorDeviceClass.POWER},
            "sensor.test_disabled_power": {
                "device_class": SensorDeviceClass.POWER,
                "disabled_by": RegistryEntryDisabler.USER,
            },
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

    assert_entity_state(hass, "sensor.test_include_power", attributes={CONF_ENTITIES: {"sensor.test_power"}})

    assert_entity_state(hass, "sensor.test_include_energy", attributes={CONF_ENTITIES: {"sensor.test_energy"}})


async def test_include_by_label(hass: HomeAssistant, label_registry: LabelRegistry) -> None:
    mock_entities_in_registry(
        hass,
        {
            "sensor.test": {"device_class": SensorDeviceClass.POWER, "labels": ["my_label"]},
            "sensor.test2": {"device_class": SensorDeviceClass.POWER, "labels": ["other_label"]},
        },
    )

    label_registry.async_create("my_label")

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

    assert_entity_state(hass, "sensor.test_include_power", attributes={CONF_ENTITIES: {"sensor.test"}})


async def test_include_by_wildcard(hass: HomeAssistant) -> None:
    mock_entities_in_registry(
        hass,
        {
            "sensor.tv_power": {"device_class": SensorDeviceClass.POWER},
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

    assert_entity_state(hass, "sensor.test_include_power", attributes={CONF_ENTITIES: {"sensor.tv_power"}})


async def test_include_by_wildcard_in_nested_groups(
    hass: HomeAssistant,
) -> None:
    mock_devices(
        hass,
        {
            "some_a-device": {"manufacturer": "lidl", "model": "HG06462A"},
            "other_b-device": {"manufacturer": "lidl", "model": "HG06462A"},
            "other_c-device": {"manufacturer": "lidl", "model": "HG06462A"},
        },
    )
    mock_entities_in_registry(
        hass,
        {
            "light.some_a": {"unique_id": "111", "device_id": "some_a-device"},
            "light.other_b": {"unique_id": "222", "device_id": "other_b-device"},
            "light.other_c": {"unique_id": "333", "device_id": "other_c-device"},
        },
    )
    await set_states(
        hass,
        [
            (entity_id, STATE_ON, DISCOVERABLE_LIGHT_ATTRIBUTES)
            for entity_id in ("light.some_a", "light.other_b", "light.other_c")
        ],
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

    assert_entity_state(
        hass,
        "sensor.test_include_a_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.some_a_power",
                "sensor.other_b_power",
                "sensor.other_c_power",
            },
        },
    )

    assert_entity_state(
        hass,
        "sensor.test_include_b_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.other_b_power",
                "sensor.other_c_power",
            },
        },
    )


async def test_include_complex_nested_filters(
    hass: HomeAssistant,
    area_registry: AreaRegistry,
) -> None:
    area = area_registry.async_get_or_create("Living room")
    mock_entities_in_registry(
        hass,
        {
            "switch.test": {},
            "switch.tv": {"area_id": area.id},
            "light.tv_ambilights": {"area_id": area.id},
            "light.living_room": {"area_id": area.id},
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

    assert_entity_state(
        hass,
        "sensor.test_include_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.tv_power",
                "sensor.tv_ambilights_power",
            },
        },
    )


async def test_include_by_area_combined_with_domain_filter(hass: HomeAssistant, area_registry: AreaRegistry) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/1984"""
    area_kitchen = area_registry.async_get_or_create("kitchen")
    area_conservatory = area_registry.async_get_or_create("conservatory")
    mock_entities_in_registry(
        hass,
        {
            "switch.kitchen_switch": {"area_id": area_kitchen.id},
            "switch.conservatory_switch": {"area_id": area_conservatory.id},
            "light.kitchen_light": {"area_id": area_kitchen.id},
            "light.conservatory_light": {"area_id": area_conservatory.id},
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

    assert_entity_state(
        hass,
        "sensor.indoor_lights_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.kitchen_light_power",
                "sensor.conservatory_light_power",
            },
        },
    )

    assert_entity_state(
        hass,
        "sensor.kitchen_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.kitchen_light_power",
            },
        },
    )

    assert_entity_state(
        hass,
        "sensor.conservatory_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.conservatory_light_power",
            },
        },
    )


async def test_include_all(hass: HomeAssistant) -> None:
    mock_entities_in_registry(
        hass,
        {
            "switch.switch": {},
            "light.light": {},
            "sensor.existing_power": {"device_class": SensorDeviceClass.POWER},
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

    assert_entity_state(
        hass,
        "sensor.all_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.switch_power",
                "sensor.light_power",
                "sensor.existing_power",
            },
        },
    )


async def test_include_by_label_filter_other_label(hass: HomeAssistant, label_registry: LabelRegistry) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/3685"""

    label_registry.async_create("my_label")
    label_registry.async_create("exclude_powercalc")

    mock_device(hass, "device-a", "Signify", "LCT012", labels=["my_label"])

    mock_entities_in_registry(
        hass,
        {
            "sensor.some_energy": {"device_id": "device-a", "original_device_class": SensorDeviceClass.ENERGY},
            "sensor.some_energy2": {
                "device_id": "device-a",
                "labels": ["exclude_powercalc"],
                "original_device_class": SensorDeviceClass.ENERGY,
            },
            "sensor.some_energy3": {
                "device_id": "device-a",
                "labels": ["exclude_powercalc"],
                "original_device_class": SensorDeviceClass.ENERGY,
            },
        },
    )

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "My group",
                CONF_INCLUDE: {
                    CONF_LABEL: "my_label",
                    CONF_FILTER: {
                        CONF_NOT: {
                            CONF_LABEL: "exclude_powercalc",
                        },
                    },
                },
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    assert_entity_state(
        hass,
        "sensor.my_group_energy",
        attributes={
            CONF_ENTITIES: {
                "sensor.some_energy",
            },
        },
    )


async def test_exclude_non_powercalc_sensors(hass: HomeAssistant) -> None:
    mock_entities_in_registry(
        hass,
        {
            "switch.switch": {},
            "sensor.existing_power": {"device_class": SensorDeviceClass.POWER},
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

    assert_entity_state(
        hass,
        "sensor.all_power",
        attributes={
            CONF_ENTITIES: {
                "sensor.switch_power",
            },
        },
    )


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

    mock_device_with_entities(hass, ["light.test", "scene.test", "event.test"], "Signify", "LCT012", platform="hue")
    result = await find_entities(hass)
    assert len(result.discoverable) == 1
    assert "light.test" in result.discoverable

    assert "scene.test" not in caplog.text
    assert "event.test" not in caplog.text


async def test_powercalc_entity_with_stale_config_entry_is_skipped(hass: HomeAssistant) -> None:
    """A Powercalc entity referencing a removed config entry must not be included."""
    mock_entities_in_registry(
        hass,
        {
            "sensor.stale_power": {
                "platform": DOMAIN,
                "config_entry_id": "non-existing-config-entry",
                "device_class": SensorDeviceClass.POWER,
            },
        },
    )

    result = await find_entities(hass)

    assert not result.resolved
    assert not result.discoverable


async def test_prevent_duplicate_entities_when_using_include_all(
    hass: HomeAssistant,
) -> None:
    mock_device_with_entities(hass, "light.test", "signify", "LCT010")

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_CREATE_GROUP: "All",
                CONF_INCLUDE: {
                    CONF_ALL: None,
                },
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    source_entity = create_source_entity("light.test", hass)
    await initialize_discovery_flow(hass, source_entity, confirm_autodiscovered_model=True)

    assert hass.states.get("sensor.test_power")
    assert not hass.states.get("sensor.test_power_2")


async def test_include_with_gui_and_yaml_entry(
    hass: HomeAssistant,
) -> None:
    """Test include works correctly when individual entity is configured both with YAML and GUI"""

    mock_device_with_entities(hass, "light.test", "signify", "LCT010")

    await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_UNIQUE_ID: "pc_68291146-1592-4cfa-b5fb-bfeefcf9c691",
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "signify",
            CONF_MODEL: "LCT015",
            CONF_CREATE_UTILITY_METERS: True,
            ENTRY_DATA_POWER_ENTITY: "sensor.test_power",
            ENTRY_DATA_ENERGY_ENTITY: "sensor.test_energy",
        },
        setup=False,
    )

    await run_powercalc_setup(
        hass,
        [
            {
                CONF_ENTITY_ID: "light.test",
            },
            {
                CONF_CREATE_GROUP: "My Group",
                CONF_INCLUDE: {
                    CONF_DOMAIN: "light",
                },
                CONF_IGNORE_UNAVAILABLE_STATE: True,
            },
        ],
    )

    assert_entity_state(hass, "sensor.my_group_power", attributes={CONF_ENTITIES: {"sensor.test_power"}})
    assert not hass.states.get("sensor.test_power2")


async def _create_powercalc_config_entry(
    hass: HomeAssistant,
    source_entity_id: str,
    unique_id: str | None = None,
) -> MockConfigEntry:
    __, object_id = split_entity_id(source_entity_id)

    return await create_mock_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: source_entity_id,
            CONF_FIXED: {CONF_POWER: 50},
            ENTRY_DATA_POWER_ENTITY: f"sensor.{object_id}_power",
            ENTRY_DATA_ENERGY_ENTITY: f"sensor.{object_id}_energy",
        },
        unique_id=unique_id,
        setup=False,
    )
