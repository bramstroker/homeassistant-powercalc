from copy import deepcopy
from datetime import timedelta

from homeassistant.const import CONF_ENTITY_ID, CONF_ID, CONF_NAME, CONF_PATH, CONF_STATE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.powercalc.configuration.config_entry_conversion import convert_config_entry_to_sensor_config
from custom_components.powercalc.const import (
    CONF_CALCULATION_ENABLED_CONDITION,
    CONF_CREATE_GROUP,
    CONF_DAILY_FIXED_ENERGY,
    CONF_FIXED,
    CONF_FORCE_ENERGY_SENSOR_CREATION,
    CONF_LINEAR,
    CONF_ON_TIME,
    CONF_PLAYBOOK,
    CONF_PLAYBOOKS,
    CONF_POWER,
    CONF_POWER_SENSOR_ID,
    CONF_POWER_TEMPLATE,
    CONF_SENSOR_TYPE,
    CONF_STATES_POWER,
    CONF_UTILITY_METER_OFFSET,
    CONF_VALUE,
    CONF_VALUE_TEMPLATE,
    SensorType,
)


def test_nested_configuration_is_converted_without_mutating_entry_data(hass: HomeAssistant) -> None:
    shared_linear_values = [0, 10]
    data = {
        CONF_FIXED: {
            CONF_POWER_TEMPLATE: "{{ 12 }}",
            CONF_STATES_POWER: [
                {CONF_STATE: "on", CONF_POWER: "{{ 20 }}"},
                {CONF_STATE: "off", CONF_POWER: 0},
            ],
        },
        CONF_LINEAR: {"calibrate": shared_linear_values},
        CONF_DAILY_FIXED_ENERGY: {
            CONF_VALUE_TEMPLATE: "{{ 1.5 }}",
            CONF_ON_TIME: {"hours": 1, "minutes": 2, "seconds": 3},
        },
        CONF_PLAYBOOK: {
            CONF_PLAYBOOKS: [{CONF_ID: "wash", CONF_PATH: "wash.csv"}],
        },
    }
    original_data = deepcopy(data)

    converted = convert_config_entry_to_sensor_config(MockConfigEntry(data=data), hass)

    assert data == original_data
    assert converted[CONF_FIXED] is not data[CONF_FIXED]
    assert converted[CONF_LINEAR] is not data[CONF_LINEAR]
    assert converted[CONF_LINEAR]["calibrate"] is shared_linear_values
    assert converted[CONF_DAILY_FIXED_ENERGY] is not data[CONF_DAILY_FIXED_ENERGY]
    assert converted[CONF_PLAYBOOK] is not data[CONF_PLAYBOOK]

    fixed = converted[CONF_FIXED]
    assert CONF_POWER_TEMPLATE not in fixed
    assert isinstance(fixed[CONF_POWER], Template)
    assert fixed[CONF_POWER].template == "{{ 12 }}"
    assert isinstance(fixed[CONF_STATES_POWER]["on"], Template)
    assert fixed[CONF_STATES_POWER]["off"] == 0

    daily_fixed = converted[CONF_DAILY_FIXED_ENERGY]
    assert CONF_VALUE_TEMPLATE not in daily_fixed
    assert isinstance(daily_fixed[CONF_VALUE], Template)
    assert daily_fixed[CONF_ON_TIME] == timedelta(hours=1, minutes=2, seconds=3)
    assert converted[CONF_PLAYBOOK][CONF_PLAYBOOKS] == {"wash": "wash.csv"}


def test_top_level_templates_and_time_deltas_are_converted(hass: HomeAssistant) -> None:
    converted = convert_config_entry_to_sensor_config(
        MockConfigEntry(
            data={
                CONF_CALCULATION_ENABLED_CONDITION: "{{ is_state('input_boolean.enable', 'on') }}",
                CONF_DAILY_FIXED_ENERGY: {CONF_VALUE: 2},
                CONF_UTILITY_METER_OFFSET: 2,
            },
        ),
        hass,
    )

    assert isinstance(converted[CONF_CALCULATION_ENABLED_CONDITION], Template)
    assert converted[CONF_DAILY_FIXED_ENERGY][CONF_ON_TIME] == timedelta(days=1)
    assert converted[CONF_UTILITY_METER_OFFSET] == timedelta(days=2)


@pytest.mark.parametrize(
    ("sensor_type", "data", "expected"),
    [
        (
            SensorType.GROUP,
            {CONF_NAME: "Kitchen"},
            {CONF_CREATE_GROUP: "Kitchen"},
        ),
        (
            SensorType.REAL_POWER,
            {CONF_ENTITY_ID: "sensor.kitchen_power"},
            {
                CONF_POWER_SENSOR_ID: "sensor.kitchen_power",
                CONF_FORCE_ENERGY_SENSOR_CREATION: True,
            },
        ),
    ],
)
def test_sensor_type_is_mapped_to_runtime_configuration(
    hass: HomeAssistant,
    sensor_type: SensorType,
    data: dict[str, object],
    expected: dict[str, object],
) -> None:
    converted = convert_config_entry_to_sensor_config(
        MockConfigEntry(data={CONF_SENSOR_TYPE: sensor_type, **data}),
        hass,
    )

    assert converted.items() >= expected.items()
