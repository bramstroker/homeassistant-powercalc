from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from functools import partial
from unittest.mock import patch

from _pytest.fixtures import SubRequest
from freezegun.api import FrozenDateTimeFactory
from homeassistant import data_entry_flow
from homeassistant.components.recorder import Recorder, migration
from homeassistant.components.recorder.db_schema import Statistics, StatisticsMeta, StatisticsShortTerm
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.tasks import PurgeTask
from homeassistant.components.utility_meter.const import DAILY
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENABLED,
    CONF_NAME,
    EVENT_HOMEASSISTANT_STARTED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfEnergy,
)
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import recorder as recorder_helper
from homeassistant.helpers.entity_registry import EntityRegistry, RegistryEntryDisabler
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from sqlalchemy import Connection, event, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Mapper, Session, object_session

from custom_components.powercalc.const import (
    CONF_CREATE_COST_SENSOR,
    CONF_CREATE_ENERGY_SENSOR,
    CONF_CREATE_UTILITY_METERS,
    CONF_DISCOVERY,
    CONF_ENERGY_PRICE,
    CONF_FORCE_CALCULATE_GROUP_ENERGY,
    CONF_GROUP_ENERGY_ENTITIES,
    CONF_GROUP_ENERGY_RECREATE_STATISTICS,
    CONF_GROUP_ENERGY_START_AT_ZERO,
    CONF_GROUP_ENERGY_UPDATE_INTERVAL,
    CONF_GROUP_POWER_ENTITIES,
    CONF_UTILITY_METER_TYPES,
    DOMAIN,
    ENTRY_DATA_ENERGY_ENTITY,
    ENTRY_DATA_GROUP_ENERGY_STATISTICS,
    SERVICE_DEBUG_GROUP,
    SERVICE_RESET_COST,
)
from custom_components.powercalc.flow_helper.common import Step
from custom_components.powercalc.flow_helper.flows.group import SECTION_GROUP_OPTIONS, create_schema_group_custom
from custom_components.powercalc.sensors.group.custom import PreviousStateStore
from custom_components.powercalc.sensors.group.statistics import async_recreate_statistics, combine_statistics
from tests.common import assert_entity_state, create_mock_group_entry
from tests.config_flow.common import section_schema, select_menu_item, submit_form_step
from tests.ha_test import (
    async_wait_purge_done,
    async_wait_recording_done,
    do_adhoc_statistics,
    statistics_during_period,
)


@pytest.fixture
def mock_recorder_before_hass(request: SubRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_db_url")
        monkeypatch.setattr(migration, "Recorder", Recorder, raising=False)
        monkeypatch.setattr(recorder_helper, "Session", Session, raising=False)


def test_combine_statistics_handles_gaps_resets_and_retention() -> None:
    result = combine_statistics(
        {
            "sensor.a": [
                {"start": 0, "state": 100, "sum": 10},
                {"start": 3600, "state": 2, "sum": 12},
            ],
            "sensor.b": [{"start": 0, "state": 20, "sum": 5}],
            "sensor.invalid": [
                {"start": 0, "state": None, "sum": 10},
                {"start": 3600, "state": 10, "sum": None},
                {"start": 7200, "state": float("inf"), "sum": 10},
                {"start": 10800, "state": 10, "sum": float("nan")},
            ],
        },
        {
            "sensor.a": [
                {"start": 3600, "state": 1, "sum": 11},
                {"start": 6900, "state": 2, "sum": 12},
            ],
            "sensor.b": [{"start": 6900, "state": 21, "sum": 6}],
        },
        dt_util.utc_from_timestamp(6900),
    )
    assert [row["sum"] for row in result.hourly] == [15, 17]
    assert [row["sum"] for row in result.short_term] == [16, 18]
    assert [row["state"] for row in result.short_term] == [16, 18]
    assert result.members == {
        "sensor.a": {"state": 2, "sum": 12, "end": 7200},
        "sensor.b": {"state": 21, "sum": 6, "end": 7200},
    }


def test_hourly_only_statistics_get_a_continuation_checkpoint() -> None:
    checkpoint_start = dt_util.utc_from_timestamp(3300)
    result = combine_statistics({"sensor.a": [{"start": 0, "state": 100, "sum": 10}]}, {}, checkpoint_start)
    assert result.hourly == [{"start": dt_util.utc_from_timestamp(0), "state": 10, "sum": 10}]
    assert result.short_term == [{"start": dt_util.utc_from_timestamp(3300), "state": 10, "sum": 10}]
    assert combine_statistics({}, {}, checkpoint_start).members == {}


async def test_recreate_statistics_and_continue_recording(
    hass: HomeAssistant,
    recorder_mock: Recorder,
    freezer: FrozenDateTimeFactory,
) -> None:
    recorder_mock.engine.echo = False
    await hass.async_start()
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=2)
    for entity_id, unit, hourly, short_term in [
        (
            "sensor.a",
            UnitOfEnergy.WATT_HOUR,
            [(0, 100000, 10000), (60, 2000, 12000)],
            [(60, 1000, 11000), (115, 2000, 12000)],
        ),
        (
            "sensor.b",
            UnitOfEnergy.KILO_WATT_HOUR,
            [(0, 20, 5)],
            [(115, 21, 6)],
        ),
    ]:
        metadata = {
            "statistic_id": entity_id,
            "source": "recorder",
            "name": None,
            "unit_of_measurement": unit,
            "unit_class": "energy",
            "has_sum": True,
            "mean_type": StatisticMeanType.NONE,
        }
        for table, rows in [(Statistics, hourly), (StatisticsShortTerm, short_term)]:
            recorder_mock.async_import_statistics(
                metadata,
                [
                    {"start": start + timedelta(minutes=minutes), "state": state, "sum": total}
                    for minutes, state, total in rows
                ],
                table,
            )
    await async_wait_recording_done(hass)

    freezer.move_to(now + timedelta(minutes=1))
    hass.states.async_set("sensor.a", "3000", {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.WATT_HOUR})
    hass.states.async_set("sensor.b", STATE_UNAVAILABLE, {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})
    hass.states.async_set("sensor.no_history", "400", {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})
    entry = await create_mock_group_entry(
        hass,
        "Historical",
        {
            CONF_CREATE_ENERGY_SENSOR: True,
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a", "sensor.b", "sensor.no_history"],
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
            CONF_GROUP_ENERGY_UPDATE_INTERVAL: 0,
        },
    )
    entity_id = "sensor.historical_energy"
    assert_entity_state(hass, entity_id, "19.0000")
    summary = entry.data[ENTRY_DATA_GROUP_ENERGY_STATISTICS]
    assert summary["hourly_records"] == 2
    assert summary["short_term_records"] == 2
    assert summary["missing_members"] == ["sensor.no_history"]
    assert summary["members"]["sensor.a"]["sum"] == 12
    debug = await hass.services.async_call(
        DOMAIN,
        SERVICE_DEBUG_GROUP,
        {"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    assert debug[entity_id]["statistics"] == summary

    # Unavailable members keep their recorded contribution; returning does not
    # count their full meter reading again. Members without history start now.
    hass.states.async_set("sensor.b", "22", {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})
    hass.states.async_set("sensor.no_history", "401", {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR})
    await hass.async_block_till_done()
    assert_entity_state(hass, entity_id, "21.0000")
    await async_wait_recording_done(hass)

    freezer.move_to(now + timedelta(minutes=6))
    do_adhoc_statistics(hass, start=now)
    await async_wait_recording_done(hass)
    short_rows = await hass.async_add_executor_job(
        lambda: statistics_during_period(hass, start, statistic_ids={entity_id}, period="5minute"),
    )
    assert [row["sum"] for row in short_rows[entity_id]] == [16, 18, 21]
    hourly_rows = await hass.async_add_executor_job(
        lambda: statistics_during_period(hass, start, statistic_ids={entity_id}, period="hour"),
    )
    assert [row["sum"] for row in hourly_rows[entity_id]] == [15, 17]

    with patch("custom_components.powercalc.sensors.group.custom.async_recreate_statistics") as recreate:
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        recreate.assert_not_called()
    assert_entity_state(hass, entity_id, "21.0000")


async def test_recreate_requires_recorder(hass: HomeAssistant) -> None:
    with pytest.raises(HomeAssistantError, match="requires Recorder"):
        await async_recreate_statistics(hass, "sensor.group", {"sensor.a"}, "kWh")


async def test_fresh_import_replaces_restore_data_for_reused_entity_id(
    hass: HomeAssistant,
    recorder_mock: Recorder,
    freezer: FrozenDateTimeFactory,
) -> None:
    recorder_mock.engine.echo = False
    await hass.async_start()
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    freezer.move_to(now + timedelta(minutes=1))
    # Advancing Recorder intervals must not also scan the unrelated profile library.
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {CONF_DISCOVERY: {CONF_ENABLED: False}}})
    attributes = {ATTR_UNIT_OF_MEASUREMENT: "kWh"}
    hass.states.async_set("sensor.a", "100", attributes)
    hass.states.async_set("sensor.no_history", "400", attributes)
    config = {
        CONF_GROUP_ENERGY_ENTITIES: ["sensor.a", "sensor.no_history"],
        CONF_GROUP_ENERGY_UPDATE_INTERVAL: 0,
    }
    old_entry = await create_mock_group_entry(hass, "Reused history", config)
    entity_id = "sensor.reused_history_energy"
    assert_entity_state(hass, entity_id, "0.0000")
    assert await hass.config_entries.async_remove(old_entry.entry_id)
    await hass.async_block_till_done()

    recorder_mock.async_import_statistics(
        {
            "statistic_id": "sensor.a",
            "source": "recorder",
            "name": None,
            "unit_of_measurement": "kWh",
            "unit_class": "energy",
            "has_sum": True,
            "mean_type": StatisticMeanType.NONE,
        },
        [{"start": now - timedelta(hours=1), "state": 100, "sum": 10}],
        Statistics,
    )
    await async_wait_recording_done(hass)
    hass.states.async_set("sensor.no_history", STATE_UNAVAILABLE, attributes)
    entry = await create_mock_group_entry(
        hass,
        "Reused history",
        {
            **config,
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
        },
    )
    assert_entity_state(hass, entity_id, "10.0000")
    hass.states.async_set("sensor.a", "102", attributes)
    hass.states.async_set("sensor.no_history", "401", attributes)
    await async_wait_recording_done(hass)
    assert_entity_state(hass, entity_id, "12.0000")

    freezer.move_to(now + timedelta(minutes=6))
    do_adhoc_statistics(hass, start=now)
    await async_wait_recording_done(hass)
    rows = await hass.async_add_executor_job(
        lambda: statistics_during_period(hass, now - timedelta(hours=1), statistic_ids={entity_id}, period="5minute"),
    )
    assert [row["sum"] for row in rows[entity_id]] == [10, 12]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert_entity_state(hass, entity_id, "12.0000")


@pytest.mark.parametrize("include_short_term", [False, True])
async def test_imported_history_survives_purge_before_first_live_statistics(
    hass: HomeAssistant,
    recorder_mock: Recorder,
    freezer: FrozenDateTimeFactory,
    include_short_term: bool,
) -> None:
    recorder_mock.engine.echo = False
    await hass.async_start()
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=30)
    metadata = {
        "statistic_id": "sensor.a",
        "source": "recorder",
        "name": None,
        "unit_of_measurement": "kWh",
        "unit_class": "energy",
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
    }
    recorder_mock.async_import_statistics(metadata, [{"start": start, "state": 100, "sum": 10}], Statistics)
    if include_short_term:
        recorder_mock.async_import_statistics(
            metadata,
            [{"start": start + timedelta(minutes=55), "state": 100, "sum": 10}],
            StatisticsShortTerm,
        )
    await async_wait_recording_done(hass)
    freezer.move_to(now + timedelta(minutes=1))
    hass.states.async_set("sensor.a", "100", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    await create_mock_group_entry(
        hass,
        "Old history",
        {
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a"],
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
            CONF_GROUP_ENERGY_UPDATE_INTERVAL: 0,
        },
    )
    entity_id = "sensor.old_history_energy"
    assert_entity_state(hass, entity_id, "10.0000")
    await async_wait_recording_done(hass)
    recorder_mock.queue_task(PurgeTask(now - timedelta(days=10), repack=False, apply_filter=False))
    await async_wait_purge_done(hass)

    hass.states.async_set("sensor.a", "102", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    await async_wait_recording_done(hass)
    assert_entity_state(hass, entity_id, "12.0000")
    freezer.move_to(now + timedelta(minutes=6))
    do_adhoc_statistics(hass, start=now)
    await async_wait_recording_done(hass)
    rows = await hass.async_add_executor_job(
        lambda: statistics_during_period(hass, start, statistic_ids={entity_id}, period="5minute"),
    )
    assert rows[entity_id][-1]["sum"] == 12
    assert [row["sum"] for row in rows[entity_id]] == [10, 12]
    assert rows[entity_id][0]["start"] == (now - timedelta(minutes=5)).timestamp()


@pytest.mark.parametrize("existing_platform", ["test", DOMAIN])
async def test_import_reserves_entity_id_occupied_by_disabled_entity(
    hass: HomeAssistant,
    recorder_mock: Recorder,
    entity_registry: EntityRegistry,
    existing_platform: str,
    freezer: FrozenDateTimeFactory,
) -> None:
    await hass.async_start()
    unrelated = entity_registry.async_get_or_create(
        "sensor",
        existing_platform,
        "unrelated_energy",
        suggested_object_id="history_energy",
        disabled_by=RegistryEntryDisabler.USER,
    )
    assert hass.states.get(unrelated.entity_id) is None
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    freezer.move_to(now + timedelta(minutes=1))
    metadata = {
        "statistic_id": "sensor.a",
        "source": "recorder",
        "name": None,
        "unit_of_measurement": "kWh",
        "unit_class": "energy",
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
    }
    for table, start in [
        (Statistics, now - timedelta(hours=1)),
        (StatisticsShortTerm, now - timedelta(minutes=5)),
    ]:
        recorder_mock.async_import_statistics(metadata, [{"start": start, "state": 100, "sum": 10}], table)
    await async_wait_recording_done(hass)
    hass.states.async_set("sensor.a", "100", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    entry = await create_mock_group_entry(
        hass,
        "History",
        {
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a"],
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
            CONF_GROUP_ENERGY_UPDATE_INTERVAL: 0,
            CONF_CREATE_UTILITY_METERS: True,
            CONF_UTILITY_METER_TYPES: [DAILY],
            CONF_CREATE_COST_SENSOR: True,
            CONF_ENERGY_PRICE: 0.25,
        },
    )
    entity_id = "sensor.history_energy_2"
    assert_entity_state(hass, entity_id, "10.0000")
    for period in ["hour", "5minute"]:
        rows = await hass.async_add_executor_job(
            partial(
                statistics_during_period,
                hass,
                now - timedelta(hours=1),
                statistic_ids={entity_id, unrelated.entity_id},
                period=period,
            ),
        )
        assert list(rows) == [entity_id]
        assert [row["sum"] for row in rows[entity_id]] == [10]
    assert entity_registry.async_get(unrelated.entity_id) == unrelated
    assert entry.data[ENTRY_DATA_ENERGY_ENTITY] == entity_id
    registered_group = entity_registry.async_get(entity_id)
    assert registered_group is not None
    assert registered_group.config_entry_id == entry.entry_id

    # Derived sensors must follow the same reserved source ID.
    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESET_COST,
        {"entity_id": "sensor.history_cost"},
        blocking=True,
    )
    hass.states.async_set("sensor.a", "102", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    await hass.async_block_till_done()
    assert_entity_state(hass, "sensor.history_energy_2_daily", "2.0000")
    assert_entity_state(hass, "sensor.history_cost", "0.5000")

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entity_registry.async_get(entity_id).id == registered_group.id
    assert entity_registry.async_get("sensor.history_energy_3") is None
    assert_entity_state(hass, entity_id, "12.0000")


@pytest.mark.parametrize("reload_count", [0, 2])
async def test_create_group_in_gui_with_hourly_history_and_reset_member(
    hass: HomeAssistant,
    recorder_mock: Recorder,
    freezer: FrozenDateTimeFactory,
    reload_count: int,
) -> None:
    await hass.async_start()
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    recorder_mock.async_import_statistics(
        {
            "statistic_id": "sensor.a",
            "source": "recorder",
            "name": None,
            "unit_of_measurement": "kWh",
            "unit_class": "energy",
            "has_sum": True,
            "mean_type": StatisticMeanType.NONE,
        },
        [{"start": now - timedelta(hours=1), "state": 100, "sum": 10}],
        Statistics,
    )
    await async_wait_recording_done(hass)
    freezer.move_to(now + timedelta(minutes=1))
    hass.states.async_set("sensor.a", STATE_UNAVAILABLE, {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    result = await select_menu_item(hass, Step.MENU_GROUP, Step.GROUP_CUSTOM)
    result = await submit_form_step(
        hass,
        result,
        {
            CONF_NAME: "History",
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a", "sensor.no_history"],
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    entity_id = "sensor.history_energy"
    for _ in range(reload_count):
        assert await hass.config_entries.async_reload(result["result"].entry_id)
        await hass.async_block_till_done()
        assert_entity_state(hass, entity_id, STATE_UNAVAILABLE)
    hass.states.async_set("sensor.a", "2", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    hass.states.async_set("sensor.no_history", "400", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    await hass.async_block_till_done()
    assert_entity_state(hass, entity_id, "12.0000")
    await async_wait_recording_done(hass)
    freezer.move_to(now + timedelta(minutes=6))
    do_adhoc_statistics(hass, start=now)
    await async_wait_recording_done(hass)
    rows = await hass.async_add_executor_job(
        lambda: statistics_during_period(hass, now - timedelta(hours=1), statistic_ids={entity_id}, period="5minute"),
    )
    assert [row["sum"] for row in rows[entity_id]] == [10, 12]
    options = section_schema(create_schema_group_custom(hass, is_option_flow=True), SECTION_GROUP_OPTIONS)
    assert CONF_GROUP_ENERGY_RECREATE_STATISTICS not in options.schema
    assert CONF_GROUP_ENERGY_START_AT_ZERO not in options.schema


@pytest.mark.parametrize("reload_storage", [False, True])
@pytest.mark.parametrize("return_state,expected_total", [("2000", 17), ("102000", 17), ("100000", 15)])
async def test_pending_member_survives_reload_and_storage_restore(
    hass: HomeAssistant,
    recorder_mock: Recorder,
    reload_storage: bool,
    return_state: str,
    expected_total: int,
) -> None:
    await hass.async_start()
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    recorder_mock.async_import_statistics(
        {
            "statistic_id": "sensor.a",
            "source": "recorder",
            "name": None,
            "unit_of_measurement": "kWh",
            "unit_class": "energy",
            "has_sum": True,
            "mean_type": StatisticMeanType.NONE,
        },
        [{"start": now - timedelta(hours=1), "state": 100, "sum": 10}],
        Statistics,
    )
    await async_wait_recording_done(hass)
    member_attributes = {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.WATT_HOUR}
    hass.states.async_set("sensor.a", STATE_UNAVAILABLE, member_attributes)
    hass.states.async_set("sensor.no_history", "400", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    entry = await create_mock_group_entry(
        hass,
        "Pending member",
        {
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a", "sensor.no_history"],
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
            CONF_GROUP_ENERGY_UPDATE_INTERVAL: 0,
        },
    )
    entity_id = "sensor.pending_member_energy"
    hass.states.async_set("sensor.no_history", "405", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    await hass.async_block_till_done()
    assert_entity_state(hass, entity_id, "15.0000")

    async def reload_group() -> None:
        assert await hass.config_entries.async_unload(entry.entry_id)
        if reload_storage:
            store = await PreviousStateStore.async_get_instance(hass)
            await store.persist_states()
            # Discard the in-memory store to load its serialized states again,
            # as on startup, while retaining HA's restored group sensor data.
            hass.data.pop("powercalc_group_storage")
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Reload repeatedly while the imported member remains unavailable. Preserve
    # both its pending checkpoint and consumption already added by other members.
    for _ in range(2):
        await reload_group()
        assert_entity_state(hass, entity_id, "15.0000")

    hass.states.async_set("sensor.a", return_state, member_attributes)
    await hass.async_block_till_done()
    assert_entity_state(hass, entity_id, f"{expected_total:.4f}")

    # Once a real reading was processed, even one equal to the imported reading,
    # later reloads must not treat the member as pending again.
    hass.states.async_set("sensor.a", STATE_UNKNOWN, member_attributes)
    await hass.async_block_till_done()
    await reload_group()
    assert_entity_state(hass, entity_id, f"{expected_total:.4f}")
    hass.states.async_set("sensor.a", "500", member_attributes)
    await hass.async_block_till_done()
    assert_entity_state(hass, entity_id, f"{expected_total:.4f}")
    hass.states.async_set("sensor.a", "1500", member_attributes)
    await hass.async_block_till_done()
    assert_entity_state(hass, entity_id, f"{expected_total + 1:.4f}")


@pytest.mark.parametrize("failure", ["database", "invalid_data"])
async def test_import_failure_does_not_mark_group_completed(
    hass: HomeAssistant,
    recorder_mock: Recorder,
    failure: str,
) -> None:
    await hass.async_start()
    with (
        patch(
            "custom_components.powercalc.sensors.group.statistics.statistics_during_period",
            return_value={
                "sensor.a": [{"start": 0, "state": 100, "sum": 10}],
            },
        ),
        patch("custom_components.powercalc.sensors.group.statistics.import_group_statistics") as import_data,
    ):
        if failure == "database":
            import_data.side_effect = SQLAlchemyError("Database unavailable")
        else:
            import_data.side_effect = ValueError("Invalid statistic")
        entry = await create_mock_group_entry(
            hass,
            "Failed import",
            {
                CONF_GROUP_ENERGY_ENTITIES: ["sensor.a"],
                CONF_GROUP_ENERGY_START_AT_ZERO: False,
                CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
            },
        )
    assert ENTRY_DATA_GROUP_ENERGY_STATISTICS not in entry.data
    assert hass.states.get("sensor.failed_import_energy") is None


@contextmanager
def simulate_statistics_import_failure(group_id: str, failure: str) -> Iterator[None]:
    """Fail after writing a statistic or immediately before committing its transaction."""

    def fail_after_statistics_insert(
        _: Mapper,
        connection: Connection,
        row: Statistics | StatisticsShortTerm,
    ) -> None:
        statistic_id = connection.scalar(
            select(StatisticsMeta.statistic_id).where(StatisticsMeta.id == row.metadata_id)
        )
        if statistic_id != group_id:
            return
        if isinstance(row, Statistics):
            if failure == "hourly":
                raise SQLAlchemyError("Hourly import failed after inserting a row")
            return
        if failure == "commit":
            session = object_session(row)
            assert session is not None
            session.info["fail_group_commit"] = True
            return
        if failure == "operational":
            raise OperationalError("INSERT statistics_short_term", {}, RuntimeError("Database unavailable"))
        raise SQLAlchemyError("Short-term import failed after inserting a row")

    def fail_before_commit(session: Session) -> None:
        session.flush()
        if session.info.get("fail_group_commit"):
            raise SQLAlchemyError("Group import commit failed")

    event.listen(Statistics, "after_insert", fail_after_statistics_insert)
    event.listen(StatisticsShortTerm, "after_insert", fail_after_statistics_insert)
    event.listen(Session, "before_commit", fail_before_commit)
    try:
        yield
    finally:
        event.remove(Statistics, "after_insert", fail_after_statistics_insert)
        event.remove(StatisticsShortTerm, "after_insert", fail_after_statistics_insert)
        event.remove(Session, "before_commit", fail_before_commit)


@pytest.mark.parametrize("failure", ["hourly", "short_term", "commit", "operational"])
async def test_partial_import_rolls_back_and_can_be_retried(
    hass: HomeAssistant,
    recorder_mock: Recorder,
    freezer: FrozenDateTimeFactory,
    failure: str,
) -> None:
    await hass.async_start()
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=1)
    metadata = {
        "statistic_id": "sensor.a",
        "source": "recorder",
        "name": None,
        "unit_of_measurement": "kWh",
        "unit_class": "energy",
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
    }
    for table, period_start in [(Statistics, start), (StatisticsShortTerm, now - timedelta(minutes=5))]:
        recorder_mock.async_import_statistics(metadata, [{"start": period_start, "state": 100, "sum": 10}], table)
    await async_wait_recording_done(hass)
    freezer.move_to(now + timedelta(minutes=1))
    hass.states.async_set("sensor.a", "100", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    group_id = "sensor.retry_history_energy"

    with simulate_statistics_import_failure(group_id, failure):
        entry = await create_mock_group_entry(
            hass,
            "Retry history",
            {
                CONF_GROUP_ENERGY_ENTITIES: ["sensor.a"],
                CONF_GROUP_ENERGY_START_AT_ZERO: False,
                CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
            },
        )

    assert ENTRY_DATA_GROUP_ENERGY_STATISTICS not in entry.data
    assert hass.states.get(group_id) is None
    await async_wait_recording_done(hass)

    def read_group_metadata() -> str | None:
        with recorder_mock.get_session() as session:
            return session.scalar(select(StatisticsMeta.statistic_id).where(StatisticsMeta.statistic_id == group_id))

    assert await recorder_mock.async_add_executor_job(read_group_metadata) is None
    for period in ["hour", "5minute"]:
        rows = await hass.async_add_executor_job(
            partial(
                statistics_during_period,
                hass,
                start,
                statistic_ids={group_id, "sensor.a"},
                period=period,
            )
        )
        assert list(rows) == ["sensor.a"]
        assert [row["sum"] for row in rows["sensor.a"]] == [10]

    # Another statistic can reuse IDs rolled back by the failed import. Stale
    # Recorder caches must not associate its rows with the group on the retry.
    for table in [Statistics, StatisticsShortTerm]:
        recorder_mock.async_import_statistics(
            {**metadata, "statistic_id": "sensor.unrelated"},
            [{"start": start, "state": 99, "sum": 99}],
            table,
        )
    await async_wait_recording_done(hass)
    hass.states.async_set("sensor.a", "102", {ATTR_UNIT_OF_MEASUREMENT: "kWh"})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert_entity_state(hass, group_id, "12.0000")
    summary = entry.data[ENTRY_DATA_GROUP_ENERGY_STATISTICS]
    assert summary["hourly_records"] == 1
    assert summary["short_term_records"] == 1
    assert summary["members"]["sensor.a"]["sum"] == 10
    await async_wait_recording_done(hass)
    freezer.move_to(now + timedelta(minutes=6))
    do_adhoc_statistics(hass, start=now)
    await async_wait_recording_done(hass)
    rows = await hass.async_add_executor_job(
        partial(
            statistics_during_period,
            hass,
            start,
            statistic_ids={group_id, "sensor.unrelated"},
            period="5minute",
        )
    )
    assert [row["sum"] for row in rows[group_id]] == [10, 12]
    assert [row["sum"] for row in rows["sensor.unrelated"]] == [99]
    hourly_rows = await hass.async_add_executor_job(
        partial(
            statistics_during_period,
            hass,
            start,
            statistic_ids={group_id},
            period="hour",
        )
    )
    assert [row["sum"] for row in hourly_rows[group_id]] == [10]


async def test_import_without_history_is_not_retried(hass: HomeAssistant, recorder_mock: Recorder) -> None:
    await hass.async_start()
    entry = await create_mock_group_entry(
        hass,
        "Empty history",
        {
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a"],
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
        },
    )
    summary = entry.data[ENTRY_DATA_GROUP_ENERGY_STATISTICS]
    assert summary["hourly_records"] == 0
    assert summary["short_term_records"] == 0
    assert summary["missing_members"] == ["sensor.a"]
    with patch("custom_components.powercalc.sensors.group.custom.async_recreate_statistics") as recreate:
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        recreate.assert_not_called()


async def test_pending_import_waits_for_home_assistant_startup(
    hass: HomeAssistant,
    recorder_mock: Recorder,
) -> None:
    await hass.async_start()
    entry = await create_mock_group_entry(
        hass,
        "Pending history",
        {
            CONF_GROUP_ENERGY_ENTITIES: ["sensor.a"],
            CONF_GROUP_ENERGY_START_AT_ZERO: False,
            CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
        },
        setup=False,
    )
    hass.set_state(CoreState.starting)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert ENTRY_DATA_GROUP_ENERGY_STATISTICS not in entry.data
    assert hass.states.get("sensor.pending_history_energy") is None
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert ENTRY_DATA_GROUP_ENERGY_STATISTICS in entry.data


@pytest.mark.parametrize(
    "options",
    [
        {CONF_GROUP_ENERGY_START_AT_ZERO: True},
        {CONF_CREATE_ENERGY_SENSOR: False},
        {CONF_FORCE_CALCULATE_GROUP_ENERGY: True},
    ],
)
async def test_setup_rejects_incompatible_statistics_configuration(
    hass: HomeAssistant,
    options: dict[str, bool],
) -> None:
    with patch("custom_components.powercalc.sensors.group.custom.async_recreate_statistics") as recreate:
        entry = await create_mock_group_entry(
            hass,
            "Invalid history",
            {
                CONF_GROUP_ENERGY_ENTITIES: ["sensor.a"],
                CONF_GROUP_POWER_ENTITIES: ["sensor.a_power"],
                CONF_GROUP_ENERGY_RECREATE_STATISTICS: True,
                CONF_GROUP_ENERGY_START_AT_ZERO: False,
                **options,
            },
        )
        recreate.assert_not_called()
    assert ENTRY_DATA_GROUP_ENERGY_STATISTICS not in entry.data
    assert hass.states.get("sensor.invalid_history_energy") is None


async def test_recreate_refuses_existing_statistics(hass: HomeAssistant, recorder_mock: Recorder) -> None:
    recorder_mock.engine.echo = False
    await hass.async_start()
    metadata = {
        "statistic_id": "sensor.group",
        "source": "recorder",
        "name": None,
        "unit_of_measurement": "kWh",
        "unit_class": "energy",
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
    }
    recorder_mock.async_import_statistics(
        metadata,
        [{"start": dt_util.utcnow().replace(minute=0, second=0, microsecond=0), "state": 7, "sum": 7}],
        Statistics,
    )
    await async_wait_recording_done(hass)
    with pytest.raises(HomeAssistantError, match="already has statistics"):
        await async_recreate_statistics(hass, "sensor.group", {"sensor.a"}, "kWh")


async def test_recreate_refuses_excluded_sensor(hass: HomeAssistant, recorder_mock: Recorder) -> None:
    with (
        patch.object(recorder_mock, "entity_filter", return_value=False),
        pytest.raises(HomeAssistantError, match="excluded from Recorder"),
    ):
        await async_recreate_statistics(hass, "sensor.group", {"sensor.a"}, "kWh")
