"""Recreate a new group's statistics from its energy members once."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
import math
from typing import Literal, TypedDict

from homeassistant.components.recorder.core import Recorder
from homeassistant.components.recorder.db_schema import Statistics, StatisticsShortTerm
from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    StatisticsRow,
    get_short_term_statistics_run_cache,
    get_start_time,
    statistics_during_period,
)
from homeassistant.components.recorder.tasks import RecorderTask
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.recorder import DATA_INSTANCE, get_instance
from homeassistant.util import dt as dt_util
from sqlalchemy.exc import SQLAlchemyError

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class MemberStatistics(TypedDict):
    state: float
    sum: float
    end: float


class StatisticsSummary(TypedDict):
    """Persisted audit of the one-time import, also used to initialize the group."""

    created_at: str
    unit_of_measurement: str
    hourly_records: int
    short_term_records: int
    members: dict[str, MemberStatistics]
    missing_members: list[str]


@dataclass
class CombinedStatistics:
    hourly: list[StatisticData] = field(default_factory=list)
    short_term: list[StatisticData] = field(default_factory=list)
    members: dict[str, MemberStatistics] = field(default_factory=dict)


def combine_statistics(
    hourly: dict[str, list[StatisticsRow]],
    short_term: dict[str, list[StatisticsRow]],
    minimum_checkpoint_start: datetime,
) -> CombinedStatistics:
    """Add cumulative sums at interval ends, carrying the last value across gaps."""
    result = CombinedStatistics()
    # Hourly rows describe the END of an hour. Do not use them to fill earlier
    # five-minute intervals within that hour. Short-term rows win at equal ends.
    events: dict[float, dict[str, MemberStatistics]] = {}
    short_term_ends: set[float] = set()
    for rows_by_member, duration in [(hourly, 3600), (short_term, 300)]:
        for entity_id, rows in rows_by_member.items():
            for row in rows:
                state, total = row.get("state"), row.get("sum")
                if state is None or total is None or not math.isfinite(state) or not math.isfinite(total):
                    continue
                end = row["start"] + duration
                events.setdefault(end, {})[entity_id] = {"state": state, "sum": total, "end": end}
                if duration == 300:
                    short_term_ends.add(end)

        # First pass builds the hourly series; the second builds the five-minute
        # series with older hourly values as a baseline for purged/missing members.
        members: dict[str, MemberStatistics] = {}
        for end, updates in sorted(events.items()):
            members.update(updates)
            if duration == 300 and end not in short_term_ends:
                continue
            record = StatisticData(
                start=dt_util.utc_from_timestamp(end - duration),
                state=sum(member["sum"] for member in members.values()),
                sum=sum(member["sum"] for member in members.values()),
            )
            (result.hourly if duration == 3600 else result.short_term).append(record)
        result.members = members
    # Keep a recent checkpoint even when all member history is old, so a purge
    # before the first live statistics run cannot discard the imported baseline.
    if result.members:
        latest_end = max(member["end"] for member in result.members.values())
        checkpoint_start = max(minimum_checkpoint_start.timestamp(), latest_end - 300)
        if checkpoint_start + 300 not in short_term_ends:
            total = sum(member["sum"] for member in result.members.values())
            result.short_term.append(
                StatisticData(start=dt_util.utc_from_timestamp(checkpoint_start), state=total, sum=total),
            )
    return result


def import_group_statistics(
    instance: Recorder,
    metadata: StatisticMetaData,
    combined: CombinedStatistics,
) -> None:
    """Insert a new group's history atomically, then publish its Recorder checkpoint."""
    if not combined.hourly and not combined.short_term:
        return

    last_short_term_id: int | None = None
    # Recorder's import_statistics commits each table separately. Use its models
    # and metadata manager in one transaction instead, so any failure rolls back
    # both tables and their metadata. The caller has ruled out existing history.
    with instance.get_session() as session, session.begin():
        metadata_manager = instance.statistics_meta_manager
        old_metadata = metadata_manager.get_many(session, statistic_ids={metadata["statistic_id"]})
        _, metadata_id = metadata_manager.update_or_add(session, metadata, old_metadata)
        session.add_all([Statistics.from_stats(metadata_id, row) for row in combined.hourly])
        short_term_rows = [StatisticsShortTerm.from_stats(metadata_id, row) for row in combined.short_term]
        session.add_all(short_term_rows)
        session.flush()
        if short_term_rows:
            # Read the generated ID before commit expires the ORM objects, so
            # updating the cache afterwards cannot trigger another database read.
            last_short_term_id = short_term_rows[-1].id

    # Publishing an uncommitted ID could leave a stale checkpoint after rollback,
    # particularly when the database reuses that ID for another statistic.
    if last_short_term_id is not None:
        get_short_term_statistics_run_cache(instance.hass).set_latest_id_for_metadata_id(
            metadata_id,
            last_short_term_id,
        )


@dataclass
class RecreateStatisticsTask(RecorderTask):
    """Serialize the snapshot and imports with Recorder's normal statistics jobs."""

    entity_id: str
    members: set[str]
    unit: str
    future: asyncio.Future[StatisticsSummary]

    def run(self, instance: Recorder) -> None:
        try:
            summary = self.recreate(instance)
        except Exception as err:  # noqa: BLE001
            # This thread boundary must report every failure to the awaiting
            # setup task; otherwise an unexpected Recorder error would hang it.
            instance.hass.loop.call_soon_threadsafe(self.future.set_exception, err)
        else:
            instance.hass.loop.call_soon_threadsafe(self.future.set_result, summary)

    def recreate(self, instance: Recorder) -> StatisticsSummary:
        hass = instance.hass
        hourly = self.read_statistics(hass, "hour")
        short_term = self.read_statistics(hass, "5minute")
        combined = combine_statistics(hourly, short_term, get_start_time())
        metadata = StatisticMetaData(
            statistic_id=self.entity_id,
            source="recorder",
            name=None,
            unit_of_measurement=self.unit,
            unit_class="energy",
            has_sum=True,
            mean_type=StatisticMeanType.NONE,
        )
        import_group_statistics(instance, metadata, combined)
        return StatisticsSummary(
            created_at=dt_util.utcnow().isoformat(),
            unit_of_measurement=self.unit,
            hourly_records=len(combined.hourly),
            short_term_records=len(combined.short_term),
            members=combined.members,
            missing_members=sorted(self.members - combined.members.keys()),
        )

    def read_statistics(
        self,
        hass: HomeAssistant,
        period: Literal["hour", "5minute"],
    ) -> dict[str, list[StatisticsRow]]:
        rows = statistics_during_period(
            hass,
            EPOCH,
            None,
            self.members | {self.entity_id},
            period,
            {"energy": self.unit},
            {"state", "sum"},
        )
        if rows.pop(self.entity_id, None):
            raise HomeAssistantError(f"Cannot recreate statistics: {self.entity_id} already has statistics")
        return rows


async def async_recreate_statistics(
    hass: HomeAssistant,
    entity_id: str,
    members: set[str],
    unit: str,
) -> StatisticsSummary:
    """Import before exposing the new sensor, so recording cannot race the import."""
    if DATA_INSTANCE not in hass.data:
        raise HomeAssistantError("Recreating group statistics requires Recorder")
    recorder = get_instance(hass)
    if recorder.entity_filter is not None and not recorder.entity_filter(entity_id):
        raise HomeAssistantError(f"Cannot recreate statistics: {entity_id} is excluded from Recorder")
    future: asyncio.Future[StatisticsSummary] = hass.loop.create_future()
    recorder.queue_task(RecreateStatisticsTask(entity_id, members, unit, future))
    try:
        return await asyncio.shield(future)
    except (SQLAlchemyError, ValueError) as err:
        raise HomeAssistantError(f"Could not recreate statistics for {entity_id}: {err}") from err
