from datetime import timedelta
from unittest.mock import PropertyMock, patch

from _pytest.fixtures import SubRequest
from freezegun import freeze_time
from homeassistant.components.recorder import Recorder, migration
from homeassistant.const import CONF_DEVICE, CONF_ENTITY_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import recorder as recorder_helper
from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry
import homeassistant.helpers.entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
    do_adhoc_statistics,
    get_start_time,
    statistics_during_period,
)
from sqlalchemy.orm import Session

from custom_components.powercalc.const import (
    CONF_CREATE_COST_SENSOR,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_STANDBY_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_ENERGY_PRICE,
    CONF_ENERGY_SENSOR_ID,
    CONF_FIXED,
    CONF_FOLLOW_DEVICE_NAME,
    CONF_MANUFACTURER,
    CONF_MODE,
    CONF_MODEL,
    CONF_POWER,
    CONF_POWER_SENSOR_FRIENDLY_NAMING,
    CONF_POWER_SENSOR_NAMING,
    CONF_SENSOR_TYPE,
    CONF_STANDBY_POWER,
    CONF_UTILITY_METER_TARIFFS,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    ENTRY_GLOBAL_CONFIG_UNIQUE_ID,
    SERVICE_CALIBRATE_ENERGY,
    CalculationStrategy,
    SensorType,
)
from custom_components.powercalc.device_naming import get_device_naming_error
from custom_components.powercalc.flow_helper.common import Step
from tests.common import create_mock_config_entry
from tests.config_flow.common import handle_options_flow_update, initialize_options_flow
from tests.config_flow.test_global_configuration import create_mock_global_config_entry


@pytest.fixture
def mock_recorder_before_hass(request: SubRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_db_url")
        # Python 3.14 evaluates this TYPE_CHECKING annotation when the plugin autospecs it.
        monkeypatch.setattr(migration, "Recorder", Recorder, raising=False)
        monkeypatch.setattr(recorder_helper, "Session", Session, raising=False)


@pytest.fixture
def source_device(
    hass: HomeAssistant,
    device_registry: DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> DeviceEntry:
    source_entry = MockConfigEntry(domain="test")
    source_entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={("test", "patio")},
        name="Patio",
    )
    entity_registry.async_get_or_create(
        "light",
        "test",
        "source",
        device_id=device.id,
        suggested_object_id="patio",
        has_entity_name=True,
        original_name=None,
    )
    hass.states.async_set("light.patio", "on", {"brightness": 255})
    return device


def entry_config() -> dict:
    return {
        CONF_NAME: "Patio",
        CONF_ENTITY_ID: "light.patio",
        CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
        CONF_MODE: CalculationStrategy.FIXED,
        CONF_FIXED: {CONF_POWER: 50},
        CONF_CREATE_ENERGY_SENSOR: True,
        CONF_CREATE_STANDBY_ENERGY_SENSOR: True,
        CONF_STANDBY_POWER: 1,
        CONF_CREATE_UTILITY_METERS: True,
        CONF_UTILITY_METER_TYPES: ["daily", "monthly"],
        CONF_CREATE_COST_SENSOR: True,
        CONF_ENERGY_PRICE: 0.30,
    }


async def set_follow_device_name(hass: HomeAssistant, enabled: bool) -> None:
    entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, ENTRY_GLOBAL_CONFIG_UNIQUE_ID)
    if entry is None:
        entry = await create_mock_global_config_entry(hass, {})
    await handle_options_flow_update(hass, entry, Step.GLOBAL_CONFIGURATION, {CONF_FOLLOW_DEVICE_NAME: enabled})
    await hass.async_block_till_done()


@pytest.mark.parametrize("tariffs", [[], ["general", "peak", "offpeak"]])
async def test_follow_device_name_lifecycle(
    hass: HomeAssistant,
    source_device: DeviceEntry,
    device_registry: DeviceRegistry,
    entity_registry: er.EntityRegistry,
    tariffs: list[str],
) -> None:
    entry = await create_mock_config_entry(hass, {**entry_config(), CONF_UTILITY_METER_TARIFFS: tariffs})
    original_entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    original_names = {item.entity_id: item.original_name for item in original_entries}
    assert entity_registry.async_get("sensor.patio_power").original_name == "Patio power"

    # Preserve a manually assigned ID, including the select used by tariff meters.
    entity_registry.async_update_entity("sensor.patio_energy", new_entity_id="sensor.my_energy")
    if tariffs:
        entity_registry.async_update_entity("select.patio_energy_daily", new_entity_id="select.my_tariff")
    await hass.async_block_till_done()
    original_ids = {
        item.unique_id: item.entity_id for item in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }

    await set_follow_device_name(hass, True)
    for device_name in ["Terrace", "Garden"]:
        device_registry.async_update_device(source_device.id, name_by_user=device_name)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.patio_power").name == f"{device_name} Power"
        assert hass.states.get("sensor.my_energy").name == f"{device_name} Energy"
        assert hass.states.get("sensor.patio_standby_energy").name == f"{device_name} Standby energy"
        assert hass.states.get("sensor.patio_cost").name == f"{device_name} Cost"
        assert hass.states.get("sensor.patio_energy_daily").name == f"{device_name} Energy daily"
        assert hass.states.get("sensor.patio_energy_daily_cost").name == f"{device_name} Energy daily cost"
        if tariffs:
            assert hass.states.get("select.my_tariff").name == f"{device_name} Energy daily"
            assert hass.states.get("sensor.patio_energy_daily_peak").name == f"{device_name} Energy daily peak"
            assert (
                hass.states.get("sensor.patio_energy_daily_peak_cost").name == f"{device_name} Energy daily peak cost"
            )
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.my_energy").name == f"{device_name} Energy"
        if tariffs:
            for tariff in ["offpeak", "peak"]:
                await hass.services.async_call(
                    "select",
                    "select_option",
                    {CONF_ENTITY_ID: "select.my_tariff", "option": tariff},
                    blocking=True,
                )
                await hass.async_block_till_done()
                assert hass.states.get(f"sensor.patio_energy_daily_{tariff}").attributes["status"] == "collecting"

    assert {
        item.unique_id: item.entity_id for item in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    } == original_ids
    assert entry.data[CONF_NAME] == entry.title == "Patio"
    assert hass.states.get("sensor.my_energy").attributes["source"] == "sensor.patio_power"

    await set_follow_device_name(hass, False)
    assert entity_registry.async_get("sensor.patio_power").original_name == original_names["sensor.patio_power"]
    assert entity_registry.async_get("sensor.my_energy").original_name == original_names["sensor.patio_energy"]
    await set_follow_device_name(hass, True)
    assert hass.states.get("sensor.my_energy").name == "Garden Energy"


async def test_user_overrides_are_preserved(
    hass: HomeAssistant,
    source_device: DeviceEntry,
    device_registry: DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    await create_mock_config_entry(hass, entry_config())
    entity_registry.async_update_entity("sensor.patio_power", name="My consumption")
    for enabled in [True, False, True]:
        await set_follow_device_name(hass, enabled)
        device_registry.async_update_device(source_device.id, name_by_user="Terrace")
        await hass.async_block_till_done()
        assert entity_registry.async_get("sensor.patio_power").name == "My consumption"
        assert "My consumption" in hass.states.get("sensor.patio_power").name


async def test_missing_device_falls_back_to_configured_names(hass: HomeAssistant) -> None:
    await create_mock_global_config_entry(hass, {CONF_FOLLOW_DEVICE_NAME: True})
    await create_mock_config_entry(hass, entry_config())
    assert hass.states.get("sensor.patio_power").name == "Patio power"
    await set_follow_device_name(hass, False)


async def test_global_naming_toggle_reloads_entries(
    hass: HomeAssistant,
    source_device: DeviceEntry,
    device_registry: DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    config = entry_config()
    entry = await create_mock_config_entry(hass, config)
    original_config = dict(entry.data)
    global_entry = await create_mock_global_config_entry(hass, {})
    assert await hass.config_entries.async_setup(global_entry.entry_id)
    await hass.async_block_till_done()
    original_ids = {
        item.unique_id: item.entity_id for item in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }
    device_registry.async_update_device(source_device.id, name_by_user="Terrace")

    for enabled in [True, False, True]:
        await handle_options_flow_update(
            hass, global_entry, Step.GLOBAL_CONFIGURATION, {CONF_FOLLOW_DEVICE_NAME: enabled}
        )
        await hass.async_block_till_done()
        power_entry = entity_registry.async_get("sensor.patio_power")
        assert power_entry.has_entity_name is enabled
        if enabled:
            assert hass.states.get("sensor.patio_power").name == "Terrace Power"
        else:
            assert power_entry.original_name == "Patio power"
        assert {
            item.unique_id: item.entity_id
            for item in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        } == original_ids
        result = await initialize_options_flow(hass, entry, Step.BASIC_OPTIONS)
        assert CONF_FOLLOW_DEVICE_NAME not in result["data_schema"].schema

    assert dict(entry.data) == original_config


async def test_global_naming_allows_editing_unsupported_entries(hass: HomeAssistant) -> None:
    await create_mock_global_config_entry(hass, {CONF_FOLLOW_DEVICE_NAME: True})
    entry = await create_mock_config_entry(hass, entry_config())
    assert hass.states.get("sensor.patio_power").name == "Patio power"
    await handle_options_flow_update(hass, entry, Step.BASIC_OPTIONS, {CONF_STANDBY_POWER: 2})
    await hass.async_block_till_done()
    assert entry.data[CONF_STANDBY_POWER] == 2
    assert CONF_FOLLOW_DEVICE_NAME not in entry.data
    assert hass.states.get("sensor.patio_power").name == "Patio power"


@pytest.mark.parametrize(
    "config,error",
    [
        ({CONF_SENSOR_TYPE: SensorType.GROUP}, "device_naming_unsupported"),
        ({CONF_DEVICE: "missing"}, "device_naming_no_device"),
        ({CONF_MODE: CalculationStrategy.MULTI_SWITCH}, "device_naming_ambiguous"),
        ({CONF_POWER_SENSOR_NAMING: "{} consumption"}, "device_naming_custom_pattern"),
        ({CONF_POWER_SENSOR_FRIENDLY_NAMING: "Power of {}"}, "device_naming_custom_pattern"),
        ({CONF_POWER_SENSOR_NAMING: "{} watts", CONF_POWER_SENSOR_FRIENDLY_NAMING: "{} power"}, None),
    ],
)
async def test_naming_eligibility(
    hass: HomeAssistant, source_device: DeviceEntry, config: dict, error: str | None
) -> None:
    entry = await create_mock_config_entry(hass, {**entry_config(), **config}, setup=False)
    assert get_device_naming_error(hass, entry.data, entry) == error


async def test_named_channels_and_multiple_entries_are_rejected(
    hass: HomeAssistant,
    source_device: DeviceEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    entry = await create_mock_config_entry(hass, entry_config(), setup=False)
    entity_registry.async_update_entity("light.patio", original_name="Left channel")
    assert get_device_naming_error(hass, entry.data, entry) == "device_naming_ambiguous"
    entity_registry.async_update_entity("light.patio", original_name=None)
    other = await create_mock_config_entry(hass, {**entry_config(), CONF_ENTITY_ID: "light.other"}, setup=False)
    assert get_device_naming_error(hass, entry.data, entry) is None
    hass.config_entries.async_update_entry(other, data={**other.data, CONF_DEVICE: source_device.id})
    assert get_device_naming_error(hass, entry.data, entry) == "device_naming_ambiguous"


async def test_global_naming_preserves_custom_patterns(
    hass: HomeAssistant, source_device: DeviceEntry, entity_registry: er.EntityRegistry
) -> None:
    await create_mock_global_config_entry(hass, {CONF_FOLLOW_DEVICE_NAME: True})
    await create_mock_config_entry(hass, {**entry_config(), CONF_POWER_SENSOR_NAMING: "{} custom"})
    assert entity_registry.async_get("sensor.patio_custom").original_name == "Patio custom"
    assert not entity_registry.async_get("sensor.patio_custom").has_entity_name


async def test_reused_energy_entity_is_untouched(
    hass: HomeAssistant,
    source_device: DeviceEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    await create_mock_global_config_entry(hass, {CONF_FOLLOW_DEVICE_NAME: True})
    energy = entity_registry.async_get_or_create("sensor", "test", "existing_energy", original_name="Existing energy")
    await create_mock_config_entry(hass, {**entry_config(), CONF_ENERGY_SENSOR_ID: energy.entity_id})
    assert entity_registry.async_get(energy.entity_id) == energy
    assert hass.states.get("sensor.patio_power").name == "Patio Power"


async def test_global_naming_preserves_profile_patterns(
    hass: HomeAssistant, source_device: DeviceEntry, entity_registry: er.EntityRegistry
) -> None:
    await create_mock_global_config_entry(hass, {CONF_FOLLOW_DEVICE_NAME: True})
    with patch(
        "custom_components.powercalc.power_profile.power_profile.PowerProfile.sensor_config",
        new_callable=PropertyMock,
        return_value={CONF_POWER_SENSOR_NAMING: "{} custom"},
    ):
        await create_mock_config_entry(hass, {**entry_config(), CONF_MANUFACTURER: "signify", CONF_MODEL: "LCT010"})
    assert entity_registry.async_get("sensor.patio_custom").original_name == "Patio custom"
    assert not entity_registry.async_get("sensor.patio_custom").has_entity_name


async def test_calibrated_energy_survives_naming_reload(hass: HomeAssistant, source_device: DeviceEntry) -> None:
    await create_mock_config_entry(hass, entry_config())
    energy_id = "sensor.patio_energy"
    await hass.services.async_call(
        DOMAIN, SERVICE_CALIBRATE_ENERGY, {CONF_ENTITY_ID: energy_id, "value": "100"}, blocking=True
    )
    for enabled in [True, False]:
        await set_follow_device_name(hass, enabled)
        assert float(hass.states.get(energy_id).state) == 100


async def test_totals_and_statistics_survive_naming_changes(
    hass: HomeAssistant,
    source_device: DeviceEntry,
    device_registry: DeviceRegistry,
    recorder_mock: Recorder,
) -> None:
    await hass.async_start()
    recorder_mock.engine.echo = False
    start = get_start_time(dt_util.utcnow()) + timedelta(minutes=5)
    with freeze_time(start) as freezer:
        await create_mock_config_entry(
            hass, {**entry_config(), CONF_FIXED: {CONF_POWER: 3600}, CONF_STANDBY_POWER: 1800}
        )
        energy_id = "sensor.patio_energy"
        for minute, state in [(1, "off"), (2, "on")]:
            freezer.move_to(start + timedelta(minutes=minute))
            hass.states.async_set("light.patio", state, {"brightness": 255})
            await async_wait_recording_done(hass)

        totals = {
            entity_id: hass.states.get(entity_id).state
            for entity_id in [
                energy_id,
                "sensor.patio_energy_daily",
                "sensor.patio_cost",
                "sensor.patio_energy_daily_cost",
            ]
        }
        assert all(float(value) > 0 for value in totals.values()), totals
        for enabled in [True, False, True]:
            await set_follow_device_name(hass, enabled)
            device_registry.async_update_device(source_device.id, name_by_user="Garden")
            await hass.async_block_till_done()
            assert {entity_id: hass.states.get(entity_id).state for entity_id in totals} == totals

        freezer.move_to(start + timedelta(minutes=6))
        do_adhoc_statistics(hass, start=start)
        await async_wait_recording_done(hass)
        hass.states.async_set("light.patio", "off", {"brightness": 255})
        await async_wait_recording_done(hass)
        final_energy = float(hass.states.get(energy_id).state)
        freezer.move_to(start + timedelta(minutes=11))
        do_adhoc_statistics(hass, start=start + timedelta(minutes=5))
        await async_wait_recording_done(hass)

        statistics = await hass.async_add_executor_job(
            lambda: statistics_during_period(hass, start, statistic_ids={energy_id}, period="5minute")
        )
        assert list(statistics) == [energy_id]
        initial_energy = float(totals[energy_id])
        assert final_energy > initial_energy
        assert [row["state"] for row in statistics[energy_id]] == [initial_energy, final_energy]
        assert statistics[energy_id][1]["sum"] - statistics[energy_id][0]["sum"] == pytest.approx(
            final_energy - initial_energy
        )
        assert hass.states.get(energy_id).name == "Garden Energy"
