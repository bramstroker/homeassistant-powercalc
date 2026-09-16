"""Small, mutually exclusive vacuum/dock profiles learned from runtime signals."""

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
import math
from statistics import median

from measure.analyser.models import (
    AnalysisContext,
    AnalysisSplit,
    FeatureReference,
    ModelConfigFragment,
    ProfileAnalysisStrategy,
    RecordingSample,
    StrategyNotApplicable,
)
from measure.analyser.vacuum_signals import (
    Activity,
    ActivitySignal,
    battery_feature,
    discover_signals,
    portable_entity,
    resolve_activity,
)

MIN_EPISODE_SAMPLES = 5
MAX_CHARGING_GAP = 20
MIN_CHARGING_SPAN = 20
CHARGING_BIN_WIDTH = 5
MIN_CHARGING_BINS = 3
MIN_SAMPLES_PER_CHARGING_BIN = 3


@dataclass(frozen=True)
class ChargingPoint:
    battery_level: int
    power: float


@dataclass(frozen=True)
class VacuumBranch:
    activity: Activity
    power: float | None = None
    calibration: tuple[ChargingPoint, ...] = ()

    @property
    def complexity(self) -> int:
        return len(self.calibration) if self.calibration else 1

    def estimate(self, sample: RecordingSample, battery: FeatureReference | None) -> float | None:
        if self.power is not None:
            return self.power
        value = battery_level(sample, battery)
        if value is None or not self.calibration[0].battery_level <= value <= self.calibration[-1].battery_level:
            return None
        levels = [point.battery_level for point in self.calibration]
        index = min(bisect_right(levels, value), len(self.calibration) - 1)
        left, right = self.calibration[index - 1], self.calibration[index]
        fraction = (value - left.battery_level) / (right.battery_level - left.battery_level)
        return left.power + (right.power - left.power) * fraction


@dataclass(frozen=True)
class VacuumCompositeCandidate:
    signals: tuple[ActivitySignal, ...]
    branches: tuple[VacuumBranch, ...]
    battery: FeatureReference | None
    context: AnalysisContext
    strategy_id: str = "vacuum_composite"

    @property
    def feature(self) -> FeatureReference:
        return self.features[0]

    @property
    def features(self) -> tuple[FeatureReference, ...]:
        features = [signal.feature for signal in self.signals]
        if self.battery is not None:
            features.append(self.battery)
        return tuple(dict.fromkeys(features))

    @property
    def complexity(self) -> int:
        return sum(branch.complexity for branch in self.branches)

    @property
    def standby_power(self) -> float | None:
        # A measured explicit docked/sleeping mode, not the minimum power of an
        # arbitrary sample, and never an unmeasured zero fallback.
        for activity in (Activity.SLEEPING, Activity.DOCKED):
            for branch in self.branches:
                if branch.activity == activity:
                    return branch.power
        return None

    def support_key(self, sample: RecordingSample) -> Activity | None:
        return resolve_activity(sample, self.signals)

    def estimate_power(self, sample: RecordingSample) -> float | None:
        activity = self.support_key(sample)
        for branch in self.branches:
            # Composite checks an overridden source's availability before its
            # condition, including when it would otherwise skip charging.
            if branch.calibration and self.battery is not None and self.battery.source == "state":
                state = sample.entities.get(self.battery.entity_id)
                if state is None or state.state in {"unknown", "unavailable"}:
                    return None
            if branch.activity == activity:
                return branch.estimate(sample, self.battery)
        return None

    def build_model_config_fragment(self) -> ModelConfigFragment:
        strategies: list[dict[str, object]] = []
        branches = {branch.activity: branch for branch in self.branches}
        for index, signal in enumerate(self.signals):
            branch = branches.get(signal.activity)
            if branch is not None:
                # Include unobserved activity flags when guarding lower-priority branches.
                strategies.append(self._branch_config(branch, signal, self.signals[:index]))
        return ModelConfigFragment("composite", "composite_config", {"mode": "stop_at_first", "strategies": strategies})

    def _branch_config(
        self, branch: VacuumBranch, signal: ActivitySignal, higher_priority: Sequence[ActivitySignal]
    ) -> dict[str, object]:
        conditions = [
            guard.condition(self.context, active=False) for guard in higher_priority if guard.feature != signal.feature
        ]
        conditions.append(signal.condition(self.context))
        item: dict[str, object] = {}
        if branch.calibration:
            assert self.battery is not None
            entity_id = portable_entity(self.battery.entity_id, self.context)
            assert entity_id is not None
            conditions.append(_charging_condition(branch, self.battery, entity_id))
            item["entity_id"] = entity_id
            linear: dict[str, object] = {
                "calibrate": [f"{point.battery_level} -> {point.power}" for point in branch.calibration]
            }
            if self.battery.source == "attribute":
                linear["attribute"] = self.battery.attribute
            item["linear"] = linear
        else:
            item["fixed"] = {"power": branch.power}
        item["condition"] = conditions[0] if len(conditions) == 1 else {"condition": "and", "conditions": conditions}
        return item


class VacuumCompositeStrategy(ProfileAnalysisStrategy):
    strategy_id = "vacuum_composite"

    def build_candidate(
        self,
        samples: Sequence[RecordingSample],
        context: AnalysisContext,
    ) -> VacuumCompositeCandidate | StrategyNotApplicable:
        if context.recipe != "vacuum_robot":
            return StrategyNotApplicable("The vacuum analyser requires the vacuum recipe")
        signals = discover_signals(samples, context)
        grouped: dict[Activity, list[RecordingSample]] = defaultdict(list)
        for sample in samples:
            if (activity := resolve_activity(sample, signals)) is not None:
                grouped[activity].append(sample)
        if len(grouped) < 2:
            return StrategyNotApplicable("Record at least two identifiable vacuum/dock activities")
        if any(sample.power < 0 for sample in samples):
            return StrategyNotApplicable("Vacuum power must be non-negative; check the meter or dummy-load correction")
        battery = battery_feature(grouped[Activity.CHARGING], context) if Activity.CHARGING in grouped else None
        branches: list[VacuumBranch] = []
        for signal in signals:
            if not (activity_samples := grouped.get(signal.activity)):
                continue
            branch = _fit_branch(signal.activity, activity_samples, battery)
            if isinstance(branch, StrategyNotApplicable):
                return branch
            branches.append(branch)
        return VacuumCompositeCandidate(signals, tuple(branches), battery, context)


def _fit_branch(
    activity: Activity, samples: Sequence[RecordingSample], battery: FeatureReference | None
) -> VacuumBranch | StrategyNotApplicable:
    if len(samples) < MIN_EPISODE_SAMPLES:
        return StrategyNotApplicable(f"Record at least {MIN_EPISODE_SAMPLES} training samples for {activity}")
    if activity == Activity.CHARGING:
        return _charging_branch(samples, battery)
    return VacuumBranch(activity, round(median(sample.power for sample in samples), 2))


def battery_level(sample: RecordingSample, feature: FeatureReference | None) -> int | None:
    value = feature.value(sample) if feature is not None else None
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        level = float(value)
        if not math.isfinite(level) or not 0 <= level <= 100:
            return None
        # Attribute-based LinearStrategy uses int(value), while numeric sensor
        # states use int(float(value)). Decimal strings are not valid attributes.
        return int(value) if feature is not None and feature.source == "attribute" else int(level)
    except ValueError:
        return None


def _charging_condition(branch: VacuumBranch, battery: FeatureReference, entity_id: str) -> dict[str, object]:
    # Guard the calibrated range: PowerCalc otherwise extrapolates. Reject
    # missing, boolean, non-finite and non-numeric values before integer coercion.
    expression = (
        f"states({entity_id!r})" if battery.source == "state" else f"state_attr({entity_id!r}, {battery.attribute!r})"
    )
    minimum_level = branch.calibration[0].battery_level
    maximum_level = branch.calibration[-1].battery_level
    checks = [
        f"{expression} is not boolean",
        f"0 <= ({expression} | float(-1)) <= 100",
        f"{minimum_level} <= ({expression} | float(-1) | int) <= {maximum_level}",
    ]
    if battery.source == "attribute":
        checks.append(
            f"({expression} is number or ({expression} is string and {expression} | trim is match('^[+-]?[0-9]+$')))"
        )
    return {"condition": "template", "value_template": "{{ " + " and ".join(checks) + " }}"}


def _charging_branch(
    samples: Sequence[RecordingSample], battery: FeatureReference | None
) -> VacuumBranch | StrategyNotApplicable:
    if battery is None:
        return StrategyNotApplicable(
            "Charging needs portable battery metadata or a matching vacuum battery_level attribute"
        )
    bins: dict[int, list[ChargingPoint]] = defaultdict(list)
    for sample in samples:
        if (level := battery_level(sample, battery)) is not None:
            bins[level // CHARGING_BIN_WIDTH].append(ChargingPoint(battery_level=level, power=sample.power))
    supported = [values for _, values in sorted(bins.items()) if len(values) >= MIN_SAMPLES_PER_CHARGING_BIN]
    if len(supported) < MIN_CHARGING_BINS:
        return StrategyNotApplicable("Charging needs at least three battery ranges with three training samples each")
    points = [
        ChargingPoint(
            battery_level=int(median(point.battery_level for point in values)),
            power=round(median(point.power for point in values), 2),
        )
        for values in supported
    ]
    points[0] = replace(points[0], battery_level=min(point.battery_level for point in supported[0]))
    points[-1] = replace(points[-1], battery_level=max(point.battery_level for point in supported[-1]))
    if points[-1].battery_level - points[0].battery_level < MIN_CHARGING_SPAN:
        return StrategyNotApplicable(f"Record charging over at least {MIN_CHARGING_SPAN} battery percentage points")
    if any(right.battery_level - left.battery_level > MAX_CHARGING_GAP for left, right in pairwise(points)):
        return StrategyNotApplicable(
            "Charging has a battery coverage gap over 20 percentage points; record a continuous charging cycle"
        )
    return VacuumBranch(Activity.CHARGING, calibration=tuple(points))


@dataclass(frozen=True)
class VacuumEpisode:
    activity: Activity | None
    samples: tuple[RecordingSample, ...]


def vacuum_episodes(samples: Sequence[RecordingSample], signals: Sequence[ActivitySignal]) -> tuple[VacuumEpisode, ...]:
    episodes: list[VacuumEpisode] = []
    current: list[RecordingSample] = []
    previous: RecordingSample | None = None
    activity: Activity | None = None
    for sample in samples:
        label = resolve_activity(sample, signals)
        boundary = previous is not None and (label != activity or sample.recording_id != previous.recording_id)
        if boundary:
            episodes.append(VacuumEpisode(activity, tuple(current)))
            current = []
        current.append(sample)
        activity, previous = label, sample
    if current:
        episodes.append(VacuumEpisode(activity, tuple(current)))
    return tuple(episodes)


def split_vacuum_samples(
    samples: Sequence[RecordingSample],
    context: AnalysisContext,
) -> AnalysisSplit | StrategyNotApplicable:
    signals = discover_signals(samples, context)
    episodes = vacuum_episodes(samples, signals)
    grouped: dict[Activity, list[VacuumEpisode]] = defaultdict(list)
    for episode in episodes:
        if episode.activity is not None:
            grouped[episode.activity].append(episode)
    if len(grouped) < 2:
        return StrategyNotApplicable("Record at least two identifiable vacuum/dock activities")
    insufficient = [
        activity
        for activity, items in grouped.items()
        if sum(len(episode.samples) >= MIN_EPISODE_SAMPLES for episode in items) < 2
    ]
    if insufficient:
        return StrategyNotApplicable(
            "Record at least two independent episodes of at least five samples for: " + ", ".join(insufficient)
        )
    # Telemetry gaps do not prove a new physical cycle. Keep same-activity
    # samples together, and reserve short episodes for validation, not fitting.
    grouped = {
        activity: [episode for episode in items if len(episode.samples) >= MIN_EPISODE_SAMPLES]
        for activity, items in grouped.items()
    }
    recordings = tuple(dict.fromkeys(sample.recording_id for sample in samples))
    if len(recordings) > 1:
        held_out = recordings[-1]
        training = tuple(sample for sample in samples if sample.recording_id != held_out)
        validation = tuple(sample for sample in samples if sample.recording_id == held_out)
        if all(
            any(episode.samples[0].recording_id == held_out for episode in items)
            and any(episode.samples[0].recording_id != held_out for episode in items)
            for items in grouped.values()
        ):
            return AnalysisSplit(training=training, validation=validation, method="held_out_recording")
    validation_ids = {
        id(sample)
        for items in grouped.values()
        for index, episode in enumerate(items)
        if index % 2 == 1
        for sample in episode.samples
    }
    # Unexplained episodes belong to validation, so missing activity coverage is
    # never hidden by dropping those samples before credibility checks.
    validation_ids.update(
        id(sample)
        for episode in episodes
        if episode.activity is None or len(episode.samples) < MIN_EPISODE_SAMPLES
        for sample in episode.samples
    )
    return AnalysisSplit(
        training=tuple(sample for sample in samples if id(sample) not in validation_ids),
        validation=tuple(sample for sample in samples if id(sample) in validation_ids),
        method="held_out_episodes",
    )
