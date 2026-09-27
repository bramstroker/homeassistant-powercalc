"""Map recorded runtime signals to canonical vacuum activities."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json

from measure.analyser.entity_references import resolve_portable_entity
from measure.analyser.models import Activity as Activity, FeatureReference, FeatureSource, ScalarStateValue
from measure.analyser.vacuum.entity_rules import (
    ATTRIBUTE_FLAGS,
    STATUS_ATTRIBUTES,
    STATUS_VALUES as ALIASES,
    EntitySignalType,
    SignalPriority,
    get_entity_signal_rule,
)
from measure.recording.models import EntityRole, RecordedEntity, RecordingContext, RecordingSample

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


def _normalise(value: ScalarStateValue) -> str:
    return str(value).strip().casefold().replace(" ", "_").replace("-", "_")


def _contains(values: Sequence[ScalarStateValue], value: ScalarStateValue) -> bool:
    # True must not accidentally match a numeric enum value of 1.
    return any(type(item) is type(value) and item == value for item in values)


@dataclass(frozen=True)
class ActivitySignal:
    activity: Activity
    feature: FeatureReference
    active: list[ScalarStateValue]
    inactive: list[ScalarStateValue]

    def matches(self, sample: RecordingSample) -> bool | None:
        value = self.feature.get_value(sample)
        if value is None:
            return None
        if _contains(self.active, value):
            return True
        return False if _contains(self.inactive, value) else None

    def build_condition(self, context: RecordingContext, *, active: bool = True) -> dict[str, object]:
        entity = resolve_portable_entity(self.feature.entity_id, context)
        assert entity is not None
        values = self.active if active else self.inactive
        if self.feature.source == FeatureSource.STATE:
            return {"condition": "state", "entity_id": entity, "state": list(values)}
        return {
            "condition": "template",
            "value_template": self._build_attribute_template(entity, values),
        }

    def _build_attribute_template(self, entity: str, values: Sequence[ScalarStateValue]) -> str:
        expression = f"state_attr({entity!r}, {self.feature.attribute!r})"
        comparisons = [
            expression + (" is sameas " if isinstance(value, bool) else " == ") + json.dumps(value) for value in values
        ]
        return "{{ " + " or ".join(comparisons or ["false"]) + " }}"


@dataclass(frozen=True)
class _SignalCandidate:
    priority: SignalPriority
    signal: ActivitySignal


@dataclass(frozen=True)
class RecordingEntitySuggestions:
    selected: list[str]
    disabled: list[str]


def suggest_recording_entities(context: RecordingContext) -> RecordingEntitySuggestions:
    """Suggest portable activity signals using metadata, before any samples exist."""
    candidates = [
        entity
        for entity in context.entities
        if entity.entity_id != context.primary_entity_id
        and entity.integration != "powercalc"
        and get_entity_signal_rule(entity) is not None
        and resolve_portable_entity(entity.entity_id, context) is not None
    ]
    available_priorities: dict[Activity, SignalPriority] = {}
    for entity in candidates:
        rule = get_entity_signal_rule(entity)
        assert rule is not None
        if (
            rule.signal_type == EntitySignalType.ACTION
            and rule.activity is not None
            and entity.disabled_by is None
            and entity.has_live_state is not False
        ):
            previous = available_priorities.get(rule.activity, rule.priority)
            available_priorities[rule.activity] = min(previous, rule.priority)
    selected: list[str] = []
    disabled: list[str] = []
    for entity in candidates:
        rule = get_entity_signal_rule(entity)
        assert rule is not None
        if rule.activity in available_priorities and rule.priority > available_priorities[rule.activity]:
            continue
        if entity.disabled_by is not None:
            disabled.append(entity.entity_id)
        elif entity.has_live_state is not False:
            selected.append(entity.entity_id)
    return RecordingEntitySuggestions(selected, disabled)


def _discover_entity_signals(
    samples: Sequence[RecordingSample],
    entities: Sequence[RecordedEntity],
    primary: str,
) -> list[_SignalCandidate]:
    candidates: list[_SignalCandidate] = []
    for entity in entities:
        feature = FeatureReference(entity.entity_id, FeatureSource.STATE)
        rule = get_entity_signal_rule(entity)
        if rule is None:
            continue
        if rule.signal_type == EntitySignalType.ACTION and rule.state_values is None:
            assert rule.activity is not None
            _add_flags(candidates, samples, feature, rule.activity, rule.priority)
        elif rule.signal_type in {EntitySignalType.ACTION, EntitySignalType.STATION}:
            assert rule.state_values is not None
            _add_aux_states(
                candidates,
                samples,
                feature,
                rule.state_values,
                rule.inactive_states,
                priority=rule.priority,
            )
        elif entity.entity_id != primary and rule.signal_type == EntitySignalType.STATUS:
            _add_states(candidates, samples, feature, rule.priority, rule.state_values)
    return candidates


def discover_signals(samples: Sequence[RecordingSample], context: RecordingContext) -> list[ActivitySignal]:
    """Find recorded states and attributes that identify vacuum and dock activities.

    Prefer dedicated activity signals and one authoritative status source, using
    entities with reusable profile placeholders. Return one signal per activity,
    ordered by activity priority for resolve_activity().
    """
    entities = [
        entity
        for entity in context.entities
        if entity.disabled_by is None
        and entity.has_live_state is not False
        and entity.integration != "powercalc"
        and resolve_portable_entity(entity.entity_id, context) is not None
    ]
    primary = context.primary_entity_id
    candidates = _discover_entity_signals(samples, entities, primary)
    attributes = {key for sample in samples if (state := sample.entities.get(primary)) for key in state.attributes}
    for attribute in sorted(attributes):
        feature = FeatureReference(primary, FeatureSource.ATTRIBUTE, attribute)
        if attribute in ATTRIBUTE_FLAGS:
            _add_flags(candidates, samples, feature, ATTRIBUTE_FLAGS[attribute], SignalPriority.ACTIVITY_FLAG)
        elif attribute in STATUS_ATTRIBUTES:
            _add_states(candidates, samples, feature, STATUS_ATTRIBUTES[attribute])
    _add_states(candidates, samples, FeatureReference(primary, FeatureSource.STATE), SignalPriority.HA_STATE)
    # Use one authoritative enum source, rather than combining a rich runtime
    # status sensor with stale vacuum attributes or the coarse HA docked state.
    status_feature = next(
        (
            candidate.signal.feature
            for candidate in sorted(candidates, key=lambda item: (item.priority, item.signal.feature.identifier))
            if candidate.priority >= SignalPriority.RELATED_STATE
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
        if candidate.priority >= SignalPriority.RELATED_STATE and signal.feature != status_feature:
            continue
        chosen.setdefault(signal.activity, signal)
    return [chosen[activity] for activity in ACTIVITY_PRIORITY if activity in chosen]


def _add_supplements(
    candidates: list[_SignalCandidate],
    samples: Sequence[RecordingSample],
    entities: Sequence[RecordedEntity],
    primary: str,
    status_activities: set[Activity],
) -> None:
    if Activity.SLEEPING not in status_activities:
        # Dreame/Mova can report charging_completed alongside an explicit sleep status.
        _add_sleep_flag(candidates, samples, FeatureReference(primary, FeatureSource.ATTRIBUTE, "status"))
        for entity in entities:
            rule = get_entity_signal_rule(entity)
            if rule is not None and rule.signal_type == EntitySignalType.STATUS and entity.translation_key == "status":
                _add_sleep_flag(
                    candidates, samples, FeatureReference(entity.entity_id, FeatureSource.STATE), rule.state_values
                )
    # Limited charging enums supplement the main status only where it has no
    # explicit charging/completion signal. A coarse HA docked state is preserved.
    for entity in entities:
        feature = FeatureReference(entity.entity_id, FeatureSource.STATE)
        rule = get_entity_signal_rule(entity)
        if rule is None:
            continue
        if rule.signal_type == EntitySignalType.CHARGING_STATUS:
            assert rule.state_values is not None
            _add_aux_states(
                candidates,
                samples,
                feature,
                rule.state_values,
                rule.inactive_states,
                priority=rule.priority,
                excluded_activities=status_activities,
            )
        elif Activity.CHARGING not in status_activities and rule.signal_type == EntitySignalType.CHARGING_FLAG:
            _add_flags(candidates, samples, feature, Activity.CHARGING, rule.priority)


def _collect_feature_values(samples: Sequence[RecordingSample], feature: FeatureReference) -> list[ScalarStateValue]:
    values: list[ScalarStateValue] = []
    for sample in samples:
        value = feature.get_value(sample)
        if (
            value is not None
            and _normalise(value) not in {"unknown", "unavailable", "none"}
            and not _contains(values, value)
        ):
            values.append(value)
    return values


def _add_flags(
    candidates: list[_SignalCandidate],
    samples: Sequence[RecordingSample],
    feature: FeatureReference,
    activity: Activity,
    priority: SignalPriority,
) -> None:
    values = _collect_feature_values(samples, feature)
    active: list[ScalarStateValue] = [
        value
        for value in values
        if value is True or (isinstance(value, str) and _normalise(value) in {"on", "active", "true"})
    ]
    inactive: list[ScalarStateValue] = [
        value
        for value in values
        if value is False
        or (isinstance(value, str) and _normalise(value) in {"off", "inactive", "false", "idle", "not_performed"})
    ]
    if active or inactive:
        candidates.append(_SignalCandidate(priority, ActivitySignal(activity, feature, active, inactive)))


def _add_sleep_flag(
    candidates: list[_SignalCandidate],
    samples: Sequence[RecordingSample],
    feature: FeatureReference,
    state_values: Mapping[Activity, frozenset[str]] | None = None,
) -> None:
    values = _collect_feature_values(samples, feature)
    state_values = ALIASES if state_values is None else state_values
    sleep_values = state_values.get(Activity.SLEEPING, frozenset())
    active: list[ScalarStateValue] = [
        value for value in values if isinstance(value, str) and _normalise(value) in sleep_values
    ]
    if active:
        candidates.append(
            _SignalCandidate(
                SignalPriority.ACTIVITY_FLAG,
                ActivitySignal(
                    Activity.SLEEPING, feature, active, [value for value in values if not _contains(active, value)]
                ),
            )
        )


def _add_aux_states(
    candidates: list[_SignalCandidate],
    samples: Sequence[RecordingSample],
    feature: FeatureReference,
    state_values: Mapping[Activity, frozenset[str]],
    off_values: frozenset[str],
    *,
    priority: SignalPriority = SignalPriority.ACTIVITY_FLAG,
    excluded_activities: set[Activity] | None = None,
) -> None:
    values = _collect_feature_values(samples, feature)
    # Include all known modes as inactive, even when only supplementing completion.
    recognised = off_values | set().union(*state_values.values())
    activities = [activity for activity in state_values if activity not in (excluded_activities or set())]
    signals: list[ActivitySignal] = []
    for activity in activities:
        active: list[ScalarStateValue] = [
            value for value in values if isinstance(value, str) and _normalise(value) in state_values[activity]
        ]
        inactive: list[ScalarStateValue] = [
            value
            for value in values
            if isinstance(value, str) and _normalise(value) in recognised and not _contains(active, value)
        ]
        if active:
            signals.append(ActivitySignal(activity, feature, active, inactive))
    # One guard is enough for an idle-only recording. Unmapped values stay unknown
    # even when no active operation was observed, instead of falling back to docked.
    if not signals and activities:
        inactive = [value for value in values if isinstance(value, str) and _normalise(value) in recognised]
        if inactive or values:
            signals.append(ActivitySignal(activities[0], feature, [], inactive))
    candidates.extend(_SignalCandidate(priority, signal) for signal in signals)


def _add_states(
    candidates: list[_SignalCandidate],
    samples: Sequence[RecordingSample],
    feature: FeatureReference,
    priority: SignalPriority,
    state_values: Mapping[Activity, frozenset[str]] | None = None,
) -> None:
    values = _collect_feature_values(samples, feature)
    state_values = ALIASES if state_values is None else state_values
    recognised = set().union(*state_values.values())
    if values and not any(isinstance(value, str) and _normalise(value) in recognised for value in values):
        # A present but unmapped status must not fall back to the coarse HA state.
        candidates.append(_SignalCandidate(priority, ActivitySignal(ACTIVITY_PRIORITY[0], feature, [], [])))
    for activity, aliases in state_values.items():
        active: list[ScalarStateValue] = [
            value for value in values if isinstance(value, str) and _normalise(value) in aliases
        ]
        if active:
            candidates.append(
                _SignalCandidate(
                    priority,
                    ActivitySignal(
                        activity,
                        feature,
                        active,
                        [
                            value
                            for value in values
                            if isinstance(value, str)
                            and _normalise(value) in recognised
                            and not _contains(active, value)
                        ],
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


def find_battery_feature(samples: Sequence[RecordingSample], context: RecordingContext) -> FeatureReference | None:
    battery = next((entity for entity in context.entities if entity.role == EntityRole.BATTERY), None)
    if battery is not None and resolve_portable_entity(battery.entity_id, context) is not None:
        return FeatureReference(battery.entity_id, FeatureSource.STATE)
    # Legacy recordings lack registry metadata, but usually expose the same battery
    # level directly on the vacuum. Never guess a related entity from its name.
    feature = FeatureReference(context.primary_entity_id, FeatureSource.ATTRIBUTE, "battery_level")
    if (
        battery is not None
        and samples
        and all(
            feature.get_value(sample) is not None
            and (state := sample.entities.get(battery.entity_id)) is not None
            and str(feature.get_value(sample)) == state.state
            for sample in samples
        )
    ):
        return feature
    return None
