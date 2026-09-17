"""Map recorded runtime signals to canonical vacuum activities."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum
import json

from measure.analyser.models import AnalysisContext, FeatureReference, RecordedEntity, RecordingSample, ScalarStateValue


class Activity(StrEnum):
    AUTO_EMPTYING = "auto_emptying"
    STATION_CLEANING = "station_cleaning"
    WASHING = "washing"
    DRYING = "drying"
    CHARGING = "charging"
    SLEEPING = "sleeping"
    COMPLETED = "completed"
    DOCKED = "docked"
    AWAY = "away"


# The first matching activity determines total wall-outlet power.
ACTIVITY_PRIORITY = (
    Activity.AUTO_EMPTYING,
    Activity.STATION_CLEANING,
    Activity.WASHING,
    Activity.DRYING,
    Activity.CHARGING,
    Activity.SLEEPING,
    Activity.COMPLETED,
    Activity.DOCKED,
    Activity.AWAY,
)
ALIASES: dict[Activity, frozenset[str]] = {
    Activity.AUTO_EMPTYING: frozenset(
        {"auto_emptying", "auto_empty", "emptying", "emptying_the_bin", "emptying_dustbin"}
    ),
    Activity.STATION_CLEANING: frozenset({"station_cleaning"}),
    Activity.WASHING: frozenset(
        {
            "washing",
            "mop_washing",
            "washing_mop",
            "washing_the_mop",
            "washing_the_mop_2",
            "clean_add_water",
            "adding_water",
        }
    ),
    Activity.DRYING: frozenset({"drying", "mop_drying", "drying_mop"}),
    Activity.CHARGING: frozenset({"charging"}),
    Activity.SLEEPING: frozenset({"sleeping", "sleep"}),
    Activity.COMPLETED: frozenset({"charging_completed", "charging_complete", "charging_done"}),
    Activity.DOCKED: frozenset({"docked"}),
    Activity.AWAY: frozenset(
        {
            "cleaning",
            "room_cleaning",
            "zone_cleaning",
            "spot_cleaning",
            "sweeping",
            "mopping",
            "sweeping_and_mopping",
            "returning",
            "returning_to_wash",
            "returning_auto_empty",
            "second_cleaning",
            "paused",
            "idle",
            "returning_to_washing",
            "building",
            "fast_mapping",
            "follow_wall_cleaning",
            "remote_control",
            "monitor_cruise",
            "monitor_spot",
            "summon_clean",
            "returning_home",
            "docking",
            "zoned_cleaning",
            "segment_cleaning",
            "going_to_wash_the_mop",
            "going_to_target",
            "mapping",
            "manual_mode",
            "remote_control_active",
            "patrol",
            "robot_status_mopping",
            "robot_status_clean_mop_cleaning",
            "robot_status_clean_mop_mopping",
            "robot_status_segment_mopping",
            "robot_status_segment_clean_mop_cleaning",
            "robot_status_segment_clean_mop_mopping",
            "robot_status_zoned_mopping",
            "robot_status_zoned_clean_mop_cleaning",
            "robot_status_zoned_clean_mop_mopping",
            "robot_status_back_to_dock_washing_duster",
        }
    ),
}


class _SourcePriority(IntEnum):
    """Prefer dedicated action signals, then the most detailed status source."""

    ACTION_ENTITY = 0
    ACTIVITY_FLAG = 1
    RELATED_STATE = 2
    RELATED_STATUS = 3
    VACUUM_STATE_ATTRIBUTE = 4
    STATUS_ATTRIBUTE = 5
    HA_STATE = 6


_ATTRIBUTE_FLAGS = {"washing": Activity.WASHING, "drying": Activity.DRYING, "auto_empty_status": Activity.AUTO_EMPTYING}
_STATUS_ENTITY_KEYS = {"state": _SourcePriority.RELATED_STATE, "status": _SourcePriority.RELATED_STATUS}
_STATUS_ATTRIBUTES = {
    "vacuum_state": _SourcePriority.VACUUM_STATE_ATTRIBUTE,
    "status": _SourcePriority.STATUS_ATTRIBUTE,
}
_ACTION_ENTITY_KEYS = {
    "auto_emptying": Activity.AUTO_EMPTYING,
    "auto_empty": Activity.AUTO_EMPTYING,
    "washing": Activity.WASHING,
    "drying": Activity.DRYING,
    "mop_washing": Activity.WASHING,
    "mop_drying": Activity.DRYING,
    "mop_drying_status": Activity.DRYING,
    "dust_emptying": Activity.AUTO_EMPTYING,
}
_STATION_KEYS = {"station_state", "self_wash_base_status"}
_STATION_ACTIVITIES = (Activity.AUTO_EMPTYING, Activity.STATION_CLEANING, Activity.WASHING, Activity.DRYING)
_CHARGING_ACTIVITIES = (Activity.CHARGING, Activity.COMPLETED)


def _normalise(value: ScalarStateValue) -> str:
    return str(value).strip().casefold().replace(" ", "_").replace("-", "_")


def _contains(values: Sequence[ScalarStateValue], value: ScalarStateValue) -> bool:
    # True must not accidentally match a numeric enum value of 1.
    return any(type(item) is type(value) and item == value for item in values)


@dataclass(frozen=True)
class ActivitySignal:
    activity: Activity
    feature: FeatureReference
    active: tuple[ScalarStateValue, ...]
    inactive: tuple[ScalarStateValue, ...]

    def matches(self, sample: RecordingSample) -> bool | None:
        value = self.feature.value(sample)
        if value is None:
            return None
        if _contains(self.active, value):
            return True
        return False if _contains(self.inactive, value) else None

    def condition(self, context: AnalysisContext, *, active: bool = True) -> dict[str, object]:
        entity = portable_entity(self.feature.entity_id, context)
        assert entity is not None
        values = self.active if active else self.inactive
        if self.feature.source == "state":
            return {"condition": "state", "entity_id": entity, "state": list(values)}
        return {
            "condition": "template",
            "value_template": self._attribute_template(entity, values),
        }

    def _attribute_template(self, entity: str, values: Sequence[ScalarStateValue]) -> str:
        expression = f"state_attr({entity!r}, {self.feature.attribute!r})"
        comparisons = [
            expression + (" is sameas " if isinstance(value, bool) else " == ") + json.dumps(value) for value in values
        ]
        return "{{ " + " or ".join(comparisons or ["false"]) + " }}"


@dataclass(frozen=True)
class _SignalCandidate:
    priority: _SourcePriority
    signal: ActivitySignal


def portable_entity(entity_id: str, context: AnalysisContext) -> str | None:
    if entity_id == context.primary_entity_id:
        return "[[entity]]"
    entity = next((entity for entity in context.entities if entity.entity_id == entity_id), None)
    primary = next((entity for entity in context.entities if entity.entity_id == context.primary_entity_id), None)
    if entity is None or primary is None or not primary.device_id or entity.device_id != primary.device_id:
        return None
    inventory = context.device_entities or context.entities
    related = [item for item in inventory if item.device_id == entity.device_id]
    if entity.translation_key and sum(item.translation_key == entity.translation_key for item in related) == 1:
        return f"[[entity_by_translation_key:{entity.translation_key}]]"
    if (
        (entity.domain == "sensor" and entity.device_class == "battery" and entity.unit == "%")
        or (entity.domain == "binary_sensor" and entity.device_class == "battery_charging")
    ) and sum(item.device_class == entity.device_class for item in related) == 1:
        return f"[[entity_by_device_class:{entity.device_class}]]"
    return None


def _entity_signals(
    samples: Sequence[RecordingSample],
    entities: Sequence[RecordedEntity],
    primary: str,
) -> list[_SignalCandidate]:
    candidates: list[_SignalCandidate] = []
    for entity in entities:
        feature = FeatureReference(entity.entity_id, "state")
        key = entity.translation_key
        if entity.domain in {"binary_sensor", "switch"} and key in _ACTION_ENTITY_KEYS:
            _add_flags(candidates, samples, feature, _ACTION_ENTITY_KEYS[str(key)], _SourcePriority.ACTION_ENTITY)
        elif entity.domain == "sensor" and entity.translation_key == "auto_empty_status":
            _add_flags(candidates, samples, feature, Activity.AUTO_EMPTYING, _SourcePriority.ACTION_ENTITY)
        elif entity.domain == "sensor" and entity.translation_key in _STATION_KEYS:
            _add_aux_states(
                candidates,
                samples,
                feature,
                _STATION_ACTIVITIES,
                {"idle", "returning"},
            )
        elif entity.entity_id != primary and entity.domain == "sensor" and key in _STATUS_ENTITY_KEYS:
            _add_states(candidates, samples, feature, _STATUS_ENTITY_KEYS[str(key)])
    return candidates


def discover_signals(samples: Sequence[RecordingSample], context: AnalysisContext) -> tuple[ActivitySignal, ...]:
    """Choose one signal per activity using portable sources and explicit priorities."""
    entities = tuple(
        entity
        for entity in context.entities
        if entity.disabled_by is None and portable_entity(entity.entity_id, context) is not None
    )
    primary = context.primary_entity_id
    candidates = _entity_signals(samples, entities, primary)
    attributes = {key for sample in samples if (state := sample.entities.get(primary)) for key in state.attributes}
    for attribute in sorted(attributes):
        feature = FeatureReference(primary, "attribute", attribute)
        if attribute in _ATTRIBUTE_FLAGS:
            _add_flags(candidates, samples, feature, _ATTRIBUTE_FLAGS[attribute], _SourcePriority.ACTIVITY_FLAG)
        elif attribute in _STATUS_ATTRIBUTES:
            _add_states(candidates, samples, feature, _STATUS_ATTRIBUTES[attribute])
    _add_states(candidates, samples, FeatureReference(primary, "state"), _SourcePriority.HA_STATE)
    # Use one authoritative enum source, rather than combining a rich runtime
    # status sensor with stale vacuum attributes or the coarse HA docked state.
    status_feature = next(
        (
            candidate.signal.feature
            for candidate in sorted(candidates, key=lambda item: (item.priority, item.signal.feature.identifier))
            if candidate.priority >= _SourcePriority.RELATED_STATE
        ),
        None,
    )
    status_activities = {
        candidate.signal.activity for candidate in candidates if candidate.signal.feature == status_feature
    }
    _add_supplements(candidates, samples, entities, primary, status_activities)
    chosen: dict[Activity, ActivitySignal] = {}
    for candidate in sorted(candidates, key=lambda item: (item.priority, item.signal.feature.identifier)):
        signal = candidate.signal
        if candidate.priority >= _SourcePriority.RELATED_STATE and signal.feature != status_feature:
            continue
        chosen.setdefault(signal.activity, signal)
    return tuple(chosen[activity] for activity in ACTIVITY_PRIORITY if activity in chosen)


def _add_supplements(
    candidates: list[_SignalCandidate],
    samples: Sequence[RecordingSample],
    entities: Sequence[RecordedEntity],
    primary: str,
    status_activities: set[Activity],
) -> None:
    if Activity.SLEEPING not in status_activities:
        # Dreame/Mova can report charging_completed alongside an explicit sleep status.
        _add_sleep_flag(candidates, samples, FeatureReference(primary, "attribute", "status"))
        for entity in entities:
            if entity.domain == "sensor" and entity.translation_key == "status":
                _add_sleep_flag(candidates, samples, FeatureReference(entity.entity_id, "state"))
    # Limited charging enums supplement the main status only where it has no
    # explicit charging/completion signal. A coarse HA docked state is preserved.
    for entity in entities:
        feature = FeatureReference(entity.entity_id, "state")
        if entity.domain == "sensor" and entity.translation_key == "charging_status":
            _add_aux_states(
                candidates,
                samples,
                feature,
                tuple(activity for activity in _CHARGING_ACTIVITIES if activity not in status_activities),
                {"not_charging", "return_to_charge"},
            )
        elif Activity.CHARGING not in status_activities and _is_charging_sensor(entity):
            _add_flags(candidates, samples, feature, Activity.CHARGING, _SourcePriority.ACTIVITY_FLAG)


def _is_charging_sensor(entity: RecordedEntity) -> bool:
    return entity.domain == "binary_sensor" and (
        (entity.translation_key == "charging_state" and entity.integration == "dreame_vacuum")
        or (entity.device_class == "battery_charging" and entity.integration == "ecovacs")
    )


def _values(samples: Sequence[RecordingSample], feature: FeatureReference) -> tuple[ScalarStateValue, ...]:
    values: list[ScalarStateValue] = []
    for sample in samples:
        value = feature.value(sample)
        if (
            value is not None
            and _normalise(value) not in {"unknown", "unavailable", "none"}
            and not _contains(values, value)
        ):
            values.append(value)
    return tuple(values)


def _add_flags(
    candidates: list[_SignalCandidate],
    samples: Sequence[RecordingSample],
    feature: FeatureReference,
    activity: Activity,
    priority: _SourcePriority,
) -> None:
    values = _values(samples, feature)
    active = tuple(
        value
        for value in values
        if value is True or (isinstance(value, str) and _normalise(value) in {"on", "active", "true"})
    )
    inactive = tuple(
        value
        for value in values
        if value is False
        or (isinstance(value, str) and _normalise(value) in {"off", "inactive", "false", "idle", "not_performed"})
    )
    if active or inactive:
        candidates.append(_SignalCandidate(priority, ActivitySignal(activity, feature, active, inactive)))


def _add_sleep_flag(
    candidates: list[_SignalCandidate], samples: Sequence[RecordingSample], feature: FeatureReference
) -> None:
    values = _values(samples, feature)
    active = tuple(
        value for value in values if isinstance(value, str) and _normalise(value) in ALIASES[Activity.SLEEPING]
    )
    if active:
        candidates.append(
            _SignalCandidate(
                _SourcePriority.ACTIVITY_FLAG,
                ActivitySignal(
                    Activity.SLEEPING, feature, active, tuple(value for value in values if not _contains(active, value))
                ),
            )
        )


def _add_aux_states(
    candidates: list[_SignalCandidate],
    samples: Sequence[RecordingSample],
    feature: FeatureReference,
    activities: Sequence[Activity],
    off_values: set[str],
) -> None:
    values = _values(samples, feature)
    recognised = off_values | set().union(*(ALIASES[activity] for activity in activities))
    # Other explicit charging modes are inactive, even when the authoritative
    # source already supplies that activity and we only supplement completion.
    if Activity.CHARGING in activities or Activity.COMPLETED in activities:
        recognised |= ALIASES[Activity.CHARGING] | ALIASES[Activity.COMPLETED]
    signals: list[ActivitySignal] = []
    for activity in activities:
        active = tuple(value for value in values if isinstance(value, str) and _normalise(value) in ALIASES[activity])
        inactive = tuple(
            value
            for value in values
            if isinstance(value, str) and _normalise(value) in recognised and not _contains(active, value)
        )
        if active:
            signals.append(ActivitySignal(activity, feature, active, inactive))
    # One inactive guard is sufficient when this recording only saw station idle.
    if not signals and activities:
        inactive = tuple(value for value in values if isinstance(value, str) and _normalise(value) in recognised)
        if inactive:
            signals.append(ActivitySignal(activities[0], feature, (), inactive))
    candidates.extend(_SignalCandidate(_SourcePriority.ACTIVITY_FLAG, signal) for signal in signals)


def _add_states(
    candidates: list[_SignalCandidate],
    samples: Sequence[RecordingSample],
    feature: FeatureReference,
    priority: _SourcePriority,
) -> None:
    values = _values(samples, feature)
    for activity, aliases in ALIASES.items():
        active = tuple(value for value in values if isinstance(value, str) and _normalise(value) in aliases)
        if active:
            candidates.append(
                _SignalCandidate(
                    priority,
                    ActivitySignal(
                        activity, feature, active, tuple(value for value in values if not _contains(active, value))
                    ),
                )
            )


def resolve_activity(sample: RecordingSample, signals: Sequence[ActivitySignal]) -> Activity | None:
    """Resolve a recorded sample to its highest-priority active vacuum/dock activity.

    Signals must be ordered by activity priority, as returned by discover_signals().
    Inactive signals are skipped. An unknown signal stops resolution: for example,
    unknown washing status prevents falling back to charging. Return None when a
    signal is unknown or no signal is active.
    """
    for signal in signals:
        matched = signal.matches(sample)
        if matched:
            return signal.activity
        if matched is None:
            return None
    return None


def battery_feature(samples: Sequence[RecordingSample], context: AnalysisContext) -> FeatureReference | None:
    battery: RecordedEntity | None = next((entity for entity in context.entities if entity.role == "battery"), None)
    if battery is not None and portable_entity(battery.entity_id, context) is not None:
        return FeatureReference(battery.entity_id, "state")
    # Legacy recordings lack registry metadata, but usually expose the same battery
    # level directly on the vacuum. Never guess a related entity from its name.
    feature = FeatureReference(context.primary_entity_id, "attribute", "battery_level")
    if (
        battery is not None
        and samples
        and all(
            feature.value(sample) is not None
            and (state := sample.entities.get(battery.entity_id)) is not None
            and str(feature.value(sample)) == state.state
            for sample in samples
        )
    ):
        return feature
    return None
