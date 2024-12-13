from homeassistant import data_entry_flow
from homeassistant.components.utility_meter.const import DAILY, WEEKLY
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME, CONF_SENSOR_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import (
    mock_device_registry,
    mock_registry,
)

from custom_components.powercalc import CONF_CREATE_UTILITY_METERS, CONF_UTILITY_METER_TARIFFS, CONF_UTILITY_METER_TYPES, SensorType
from custom_components.powercalc.config_flow import Step
from tests.config_flow.common import (
    create_mock_entry,
    initialize_options_flow,
    select_menu_item,
)


async def test_real_power(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.REAL_POWER)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Washing machine",
            CONF_ENTITY_ID: "sensor.washing_machine_power",
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    # Submit utility meter options step with default settings
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_UTILITY_METER_TYPES: [DAILY],
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()
    assert hass.states.get("sensor.washing_machine_energy")
    assert hass.states.get("sensor.washing_machine_energy_daily")


async def test_energy_sensor_is_bound_to_power_device(hass: HomeAssistant) -> None:
    power_sensor_id = "sensor.my_power"
    device_id = "test"

    entity_registry = mock_registry(
        hass,
        {
            power_sensor_id: RegistryEntry(
                entity_id=power_sensor_id,
                unique_id="123",
                platform="sensor",
                device_id=device_id,
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            device_id: DeviceEntry(
                id=device_id,
                manufacturer="foo",
                model="bar",
            ),
        },
    )

    result = await select_menu_item(hass, Step.REAL_POWER)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: power_sensor_id,
            CONF_CREATE_UTILITY_METERS: False,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    config_entry: ConfigEntry = result["result"]

    await hass.async_block_till_done()

    energy_sensor_entry = entity_registry.async_get("sensor.test_energy")
    assert energy_sensor_entry
    assert energy_sensor_entry.unique_id == f"{config_entry.unique_id}_energy"
    assert energy_sensor_entry.device_id == device_id


async def test_real_power_options(hass: HomeAssistant) -> None:
    entry = create_mock_entry(
        hass,
        {
            CONF_NAME: "Some name",
            CONF_ENTITY_ID: "sensor.my_real_power",
            CONF_SENSOR_TYPE: SensorType.REAL_POWER,
            CONF_CREATE_UTILITY_METERS: False,
        },
    )

    result = await initialize_options_flow(hass, entry, Step.BASIC_OPTIONS)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_CREATE_UTILITY_METERS: True},
    )

    result = await initialize_options_flow(hass, entry, Step.REAL_POWER)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_ENTITY_ID: "sensor.my_new_real_power"},
    )

    await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_ENTITY_ID] == "sensor.my_new_real_power"
    assert entry.data[CONF_CREATE_UTILITY_METERS]

    state = hass.states.get("sensor.some_name_energy")
    assert state
    assert state.attributes.get("source") == "sensor.my_new_real_power"


async def test_attach_to_custom_device(hass: HomeAssistant) -> None:
    """See https://github.com/bramstroker/homeassistant-powercalc/issues/2046"""

    power_sensor_id = "sensor.my_smart_plug"
    device_id = "media_player.my_tv"

    entity_registry = mock_registry(
        hass,
        {
            power_sensor_id: RegistryEntry(
                entity_id=power_sensor_id,
                unique_id="123",
                platform="sensor",
            ),
        },
    )
    mock_device_registry(
        hass,
        {
            device_id: DeviceEntry(
                id=device_id,
                manufacturer="foo",
                model="bar",
                identifiers={("sensor", "identifier_test")},
                connections={("mac", "30:31:32:33:34:35")},
            ),
        },
    )

    result = await select_menu_item(hass, Step.REAL_POWER)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.my_smart_plug",
            CONF_DEVICE: device_id,
        },
    )

    await hass.async_block_till_done()

    energy_sensor_entry = entity_registry.async_get("sensor.test_energy")
    assert energy_sensor_entry.device_id == device_id


async def test_no_error_is_raised_when_device_not_exists(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.REAL_POWER)
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.my_smart_plug",
            CONF_DEVICE: "non_existing",
        },
    )

    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_energy")


async def test_create_utility_meter_tariff_sensors(hass: HomeAssistant) -> None:
    result = await select_menu_item(hass, Step.REAL_POWER)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Test",
            CONF_ENTITY_ID: "sensor.my_smart_plug",
            CONF_CREATE_UTILITY_METERS: True,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == Step.UTILITY_METER_OPTIONS

    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_UTILITY_METER_TARIFFS: ["peak", "offpeak"],
            CONF_UTILITY_METER_TYPES: [DAILY, WEEKLY],
        },
    )

    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_energy")
    assert hass.states.get("select.test_energy_daily")
    assert hass.states.get("sensor.test_energy_daily_peak")
    assert hass.states.get("sensor.test_energy_daily_offpeak")
    assert hass.states.get("sensor.test_energy_weekly_peak")
    assert hass.states.get("sensor.test_energy_weekly_offpeak")
