"""Small, mutually exclusive vacuum/dock profiles learned from runtime signals."""

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
import math
from statistics import mean, median

from measure.analyser.entity_references import resolve_portable_entity
from measure.analyser.models import (
    AnalysisCandidate,
    FeatureReference,
    FeatureSource,
    ModelConfigFragment,
    ProfileAnalysisStrategy,
    StrategyNotApplicable,
    TrainingValidationSplit,
    ValidationMethod,
)
from measure.analyser.sample_intervals import calculate_sample_durations
from measure.analyser.vacuum.signals import (
    Activity,
    ActivitySignal,
    discover_signals,
    find_battery_feature,
    resolve_activity,
)
from measure.recording.models import RecorderProfileRecipe, RecordingContext, RecordingSample

MIN_EPISODE_SAMPLES = 5
MAX_CHARGING_GAP = 20
MIN_CHARGING_SPAN = 20
CHARGING_BIN_WIDTH = 5
MIN_CHARGING_BINS = 3
MIN_SAMPLES_PER_CHARGING_BIN = 3
#: Held-out charging must rise over this many battery percentage points, so a
#: trickle at one level cannot stand in for an independent charge.
MIN_VALIDATION_CHARGING_SPAN = 10
#: A held-out recording must cover this share of every activity's recorded time, so
#: a few seconds of an activity cannot decide whether its model is credible.
MIN_HELD_OUT_SHARE = 0.1


@dataclass(frozen=True)
class ChargingPoint:
    battery_level: int
    power: float


@dataclass(frozen=True)
class FixedBranch:
    activity: Activity
    power: float

    @property
    def complexity(self) -> int:
        return 1

    def estimate(self, sample: RecordingSample, battery: FeatureReference | None) -> float:
        return self.power


@dataclass(frozen=True)
class ChargingBranch:
    calibration: list[ChargingPoint]
    activity: Activity = field(default=Activity.CHARGING, init=False)

    def __post_init__(self) -> None:
        if len(self.calibration) < 2:
            raise ValueError("A charging curve needs at least two calibration points")
        if any(right.battery_level <= left.battery_level for left, right in pairwise(self.calibration)):
            raise ValueError("Charging calibration battery levels must be strictly increasing")

    @property
    def complexity(self) -> int:
        return len(self.calibration)

    def estimate(self, sample: RecordingSample, battery: FeatureReference | None) -> float | None:
        value = get_battery_level(sample, battery)
        if value is None or not self.calibration[0].battery_level <= value <= self.calibration[-1].battery_level:
            return None
        levels = [point.battery_level for point in self.calibration]
        index = min(bisect_right(levels, value), len(self.calibration) - 1)
        left, right = self.calibration[index - 1], self.calibration[index]
        fraction = (value - left.battery_level) / (right.battery_level - left.battery_level)
        return left.power + (right.power - left.power) * fraction


type VacuumBranch = FixedBranch | ChargingBranch


@dataclass(frozen=True)
class VacuumCompositeCandidate:
    signals: list[ActivitySignal]
    branches: list[VacuumBranch]
    battery: FeatureReference | None
    context: RecordingContext
    strategy_id: str = "vacuum_composite"

    @property
    def feature(self) -> FeatureReference:
        return self.features[0]

    @property
    def features(self) -> list[FeatureReference]:
        features = [feature for signal in self.signals for feature in signal.features]
        if self.battery is not None:
            features.append(self.battery)
        return list(dict.fromkeys(features))

    @property
    def complexity(self) -> int:
        return sum(branch.complexity for branch in self.branches)

    @property
    def standby_power(self) -> float | None:
        # A measured explicit docked/sleeping mode, not the minimum power of an
        # arbitrary sample, and never an unmeasured zero fallback.
        for activity in (Activity.SLEEPING, Activity.DOCKED):
            for branch in self.branches:
                if isinstance(branch, FixedBranch) and branch.activity == activity:
                    return branch.power
        return None

    def get_support_key(self, sample: RecordingSample) -> Activity | None:
        return resolve_activity(sample, self.signals)

    def estimate_power(self, sample: RecordingSample) -> float | None:
        return self.estimate_activity_power(sample, self.get_support_key(sample))

    def estimate_activity_power(self, sample: RecordingSample, activity: Activity | None) -> float | None:
        """Estimate a sample whose activity has already been resolved."""
        for branch in self.branches:
            # Composite checks an overridden source's availability before its
            # condition, including when it would otherwise skip charging.
            if (
                isinstance(branch, ChargingBranch)
                and self.battery is not None
                and self.battery.source == FeatureSource.STATE
            ):
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
                strategies.append(self._build_branch_config(branch, signal, self.signals[:index]))
        return ModelConfigFragment("composite", "composite_config", {"mode": "stop_at_first", "strategies": strategies})

    def _build_branch_config(
        self, branch: VacuumBranch, signal: ActivitySignal, higher_priority: Sequence[ActivitySignal]
    ) -> dict[str, object]:
        conditions = [
            guard.build_condition(self.context, active=False)
            for guard in higher_priority
            if guard.feature != signal.feature
        ]
        conditions.append(signal.build_condition(self.context))
        item: dict[str, object] = {}
        if isinstance(branch, ChargingBranch):
            assert self.battery is not None
            entity_id = resolve_portable_entity(self.battery.entity_id, self.context)
            assert entity_id is not None
            conditions.append(_build_charging_condition(branch, self.battery, entity_id))
            item["entity_id"] = entity_id
            linear: dict[str, object] = {
                "calibrate": [f"{point.battery_level} -> {point.power}" for point in branch.calibration]
            }
            if self.battery.source == FeatureSource.ATTRIBUTE:
                linear["attribute"] = self.battery.attribute
            item["linear"] = linear
        else:
            item["fixed"] = {"power": branch.power}
        item["condition"] = conditions[0] if len(conditions) == 1 else {"condition": "and", "conditions": conditions}
        return item


class VacuumCompositeStrategy(ProfileAnalysisStrategy):
    strategy_id = "vacuum_composite"

    def build_candidates(
        self,
        samples: Sequence[RecordingSample],
        context: RecordingContext,
        signals: Sequence[ActivitySignal],
        *,
        recording_samples: Sequence[RecordingSample] | None = None,
    ) -> list[AnalysisCandidate] | StrategyNotApplicable:
        if context.recipe != RecorderProfileRecipe.VACUUM_ROBOT:
            return StrategyNotApplicable("The vacuum analyser requires the vacuum recipe")
        grouped: dict[Activity, list[RecordingSample]] = defaultdict(list)
        for sample in samples:
            if (activity := resolve_activity(sample, signals)) is not None:
                grouped[activity].append(sample)
        if len(grouped) < 2:
            return StrategyNotApplicable("Record at least two identifiable vacuum/dock activities")
        if any(sample.power < 0 for sample in samples):
            return StrategyNotApplicable("Vacuum power must be non-negative; check the meter or dummy-load correction")
        battery = find_battery_feature(grouped[Activity.CHARGING], context) if Activity.CHARGING in grouped else None
        original_samples = samples if recording_samples is None else recording_samples
        branches: list[VacuumBranch] = []
        for signal in signals:
            if not (activity_samples := grouped.get(signal.activity)):
                continue
            durations = calculate_sample_durations(original_samples, activity_samples)
            branch = _fit_branch(signal.activity, activity_samples, battery, durations)
            if isinstance(branch, StrategyNotApplicable):
                if signal.activity == Activity.CHARGING and _has_overlapping_charge(original_samples, signals, battery):
                    return StrategyNotApplicable(
                        "Drying overlaps the battery rise, leaving too little isolated charging data. "
                        "Record one continuous charge with mop drying switched off, from a low battery through "
                        "to full. Existing recordings can stay in this session."
                    )
                return branch
            branches.append(branch)
        return [VacuumCompositeCandidate(list(signals), branches, battery, context)]


def _fit_branch(
    activity: Activity,
    samples: Sequence[RecordingSample],
    battery: FeatureReference | None,
    durations: Mapping[int, float],
) -> VacuumBranch | StrategyNotApplicable:
    if len(samples) < MIN_EPISODE_SAMPLES:
        return StrategyNotApplicable(f"Record at least {MIN_EPISODE_SAMPLES} training samples for {activity}")
    if activity == Activity.CHARGING:
        return _fit_charging_branch(samples, battery)
    # A fixed power must preserve energy: a median would pick the heater-on level of
    # a cycling dryer, or ignore the start-up ramp of a short bin emptying.
    return FixedBranch(activity, round(calculate_average_power(samples, durations), 2))


def _has_overlapping_charge(
    samples: Sequence[RecordingSample], signals: Sequence[ActivitySignal], battery: FeatureReference | None
) -> bool:
    charging = next(signal for signal in signals if signal.activity == Activity.CHARGING)
    levels = [
        level
        for sample in samples
        if (
            (activity := resolve_activity(sample, signals)) == Activity.DRYING_WHILE_CHARGING
            or (activity == Activity.DRYING and charging.matches(sample))
        )
        and (level := get_battery_level(sample, battery)) is not None
    ]
    return bool(levels) and max(levels) - min(levels) >= MIN_CHARGING_SPAN


def calculate_average_power(samples: Sequence[RecordingSample], durations: Mapping[int, float]) -> float:
    """Time-weighted mean power; the plain mean when no reading represents any time."""
    total_duration = sum(durations.get(id(sample), 0.0) for sample in samples)
    if total_duration == 0:
        return mean(sample.power for sample in samples)
    return sum(sample.power * durations.get(id(sample), 0.0) for sample in samples) / total_duration


def get_battery_level(sample: RecordingSample, feature: FeatureReference | None) -> int | None:
    value = feature.get_value(sample) if feature is not None else None
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        level = float(value)
        if not math.isfinite(level) or not 0 <= level <= 100:
            return None
        # Attribute-based LinearStrategy uses int(value), while numeric sensor
        # states use int(float(value)). Decimal strings are not valid attributes.
        return int(value) if feature is not None and feature.source == FeatureSource.ATTRIBUTE else int(level)
    except ValueError:
        return None


def _build_charging_condition(branch: ChargingBranch, battery: FeatureReference, entity_id: str) -> dict[str, object]:
    # Guard the calibrated range: PowerCalc otherwise extrapolates. Reject
    # missing, boolean, non-finite and non-numeric values before integer coercion.
    expression = (
        f"states({entity_id!r})"
        if battery.source == FeatureSource.STATE
        else f"state_attr({entity_id!r}, {battery.attribute!r})"
    )
    minimum_level = branch.calibration[0].battery_level
    maximum_level = branch.calibration[-1].battery_level
    checks = [
        f"{expression} is not boolean",
        f"0 <= ({expression} | float(-1)) <= 100",
        f"{minimum_level} <= ({expression} | float(-1) | int) <= {maximum_level}",
    ]
    if battery.source == FeatureSource.ATTRIBUTE:
        checks.append(
            f"({expression} is number or ({expression} is string and {expression} | trim is match('^[+-]?[0-9]+$')))"
        )
    return {"condition": "template", "value_template": "{{ " + " and ".join(checks) + " }}"}


def _fit_charging_branch(
    samples: Sequence[RecordingSample], battery: FeatureReference | None
) -> ChargingBranch | StrategyNotApplicable:
    if battery is None:
        return StrategyNotApplicable(
            "Charging needs portable battery metadata or a matching vacuum battery_level attribute"
        )
    bins: dict[int, list[ChargingPoint]] = defaultdict(list)
    for sample in samples:
        if (level := get_battery_level(sample, battery)) is not None:
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
    return ChargingBranch(calibration=points)


@dataclass(frozen=True)
class VacuumEpisode:
    activity: Activity | None
    samples: list[RecordingSample]


def group_vacuum_episodes(samples: Sequence[RecordingSample], signals: Sequence[ActivitySignal]) -> list[VacuumEpisode]:
    episodes: list[VacuumEpisode] = []
    current: list[RecordingSample] = []
    previous: RecordingSample | None = None
    activity: Activity | None = None
    for sample in samples:
        label = resolve_activity(sample, signals)
        boundary = previous is not None and (label != activity or sample.recording_id != previous.recording_id)
        if boundary:
            episodes.append(VacuumEpisode(activity, current))
            current = []
        current.append(sample)
        activity, previous = label, sample
    if current:
        episodes.append(VacuumEpisode(activity, current))
    return episodes


def split_vacuum_samples(
    samples: Sequence[RecordingSample],
    context: RecordingContext,
) -> TrainingValidationSplit | StrategyNotApplicable:
    signals = discover_signals(samples, context)
    episodes = group_vacuum_episodes(samples, signals)
    grouped: dict[Activity, list[VacuumEpisode]] = defaultdict(list)
    for episode in episodes:
        if episode.activity is not None:
            grouped[episode.activity].append(episode)
    if len(grouped) < 2:
        return StrategyNotApplicable("Record at least two identifiable vacuum/dock activities")
    # Telemetry gaps do not prove a new physical cycle. Keep same-activity
    # samples together, and reserve short episodes for validation, not fitting.
    charges = _group_charges(episodes)
    if charges:
        grouped[Activity.CHARGING] = charges
    grouped = {
        activity: [episode for episode in items if len(episode.samples) >= MIN_EPISODE_SAMPLES]
        for activity, items in grouped.items()
    }
    recording_split = _try_split_by_recording(samples, grouped, signals)
    if recording_split is not None:
        split = recording_split
        fallback_activities: set[Activity] = set()
    else:
        split = _split_by_episode(samples, episodes, grouped, signals)
        fallback_activities = {activity for activity, items in grouped.items() if len(items) < 2}
        fallback_activities.update(_find_brief_activity_validation(samples, grouped, split))
    # Charging needs its own hold-out when the shared split leaves it untestable,
    # without giving up the independent split of the other activities.
    if not _supports_charging_split(split, context, charges):
        charging_split = _try_split_charging_cycles(samples, episodes, charges, split, context)
        if charging_split is None:
            fallback_activities.add(Activity.CHARGING)
        else:
            split = charging_split
            fallback_activities.discard(Activity.CHARGING)
    if not fallback_activities:
        return split
    split = _split_within_activities(samples, episodes, split, fallback_activities, context)
    if not split.training:
        return StrategyNotApplicable(
            "No samples remain for fitting after holding out validation data; "
            "record longer, complete vacuum/dock activities with enough readings for both fitting and validation."
        )
    return split


def _find_brief_activity_validation(
    samples: Sequence[RecordingSample],
    grouped: Mapping[Activity, list[VacuumEpisode]],
    split: TrainingValidationSplit,
) -> set[Activity]:
    """Short snippets cannot validate a much longer fixed-power activity."""
    validation_ids = {id(sample) for sample in split.validation}
    brief: set[Activity] = set()
    for activity, episodes in grouped.items():
        if activity == Activity.CHARGING:
            continue
        activity_samples = [sample for episode in episodes for sample in episode.samples]
        held_out = [sample for sample in activity_samples if id(sample) in validation_ids]
        total_seconds = sum(calculate_sample_durations(samples, activity_samples).values())
        held_out_seconds = sum(calculate_sample_durations(samples, held_out).values())
        if held_out_seconds < MIN_HELD_OUT_SHARE * total_seconds:
            brief.add(activity)
    return brief


def _supports_charging_split(
    split: TrainingValidationSplit, context: RecordingContext, charges: Sequence[VacuumEpisode]
) -> bool:
    """Require a covered, independent charge that actually rises over a usable battery range."""
    training = [sample for sample in split.training if resolve_activity(sample, split.signals) == Activity.CHARGING]
    validation = [sample for sample in split.validation if resolve_activity(sample, split.signals) == Activity.CHARGING]
    if not training and not validation:
        return True
    battery = find_battery_feature(training, context)
    branch = _fit_charging_branch(training, battery)
    if isinstance(branch, StrategyNotApplicable):
        return False
    validation_ids = {id(sample) for sample in validation}
    has_rising_charge = False
    for charge in charges:
        if any(id(sample) not in validation_ids for sample in charge.samples):
            continue
        levels = [level for sample in charge.samples if (level := get_battery_level(sample, battery)) is not None]
        if len(levels) >= MIN_EPISODE_SAMPLES and levels[-1] - levels[0] >= MIN_VALIDATION_CHARGING_SPAN:
            has_rising_charge = True
            break
    if not has_rising_charge:
        return False
    covered = sum(branch.estimate(sample, battery) is not None for sample in validation)
    return covered >= 0.9 * len(validation)


@dataclass(frozen=True)
class ChargingHoldOut:
    sample_ids: frozenset[int]
    method: ValidationMethod


def _try_split_charging_cycles(
    samples: Sequence[RecordingSample],
    episodes: Sequence[VacuumEpisode],
    charges: Sequence[VacuumEpisode],
    split: TrainingValidationSplit,
    context: RecordingContext,
) -> TrainingValidationSplit | None:
    """Hold out independent charging while keeping the other activities' validation from `split`.

    Short charging episodes always stay in validation. The first candidate whose
    battery range the remaining charges cover wins.
    """
    charging_ids: set[int] = set()
    short_episode_ids: set[int] = set()
    for episode in episodes:
        if episode.activity != Activity.CHARGING:
            continue
        for sample in episode.samples:
            charging_ids.add(id(sample))
            if len(episode.samples) < MIN_EPISODE_SAMPLES:
                short_episode_ids.add(id(sample))
    other_validation_ids = {id(sample) for sample in split.validation if id(sample) not in charging_ids}
    for hold_out in _list_charging_hold_outs(charges, split.method, short_episode_ids):
        validation_ids = other_validation_ids | short_episode_ids | hold_out.sample_ids
        candidate = TrainingValidationSplit(
            training=[sample for sample in samples if id(sample) not in validation_ids],
            validation=[sample for sample in samples if id(sample) in validation_ids],
            method=hold_out.method,
            signals=split.signals,
        )
        if _supports_charging_split(candidate, context, charges):
            return candidate
    return None


def _list_charging_hold_outs(
    charges: Sequence[VacuumEpisode], method: ValidationMethod | None, short_episode_ids: set[int]
) -> list[ChargingHoldOut]:
    """List distinct charging hold-outs: whole recordings first, then single charges, latest first.

    Keep `HELD_OUT_RECORDING` only when the other activities were also held out by recording.
    """
    recording_method = (
        ValidationMethod.HELD_OUT_RECORDING
        if method == ValidationMethod.HELD_OUT_RECORDING
        else ValidationMethod.HELD_OUT_EPISODES
    )
    charging_by_recording: dict[int, set[int]] = defaultdict(set)
    for charge in charges:
        charging_by_recording[charge.samples[0].recording_id].update(id(sample) for sample in charge.samples)
    hold_outs: list[ChargingHoldOut] = []
    if len(charging_by_recording) > 1:
        hold_outs.extend(
            ChargingHoldOut(frozenset(sample_ids - short_episode_ids), recording_method)
            for sample_ids in reversed(charging_by_recording.values())
        )
    for charge in reversed(charges):
        sample_ids = {id(sample) for sample in charge.samples}
        hold_outs.append(ChargingHoldOut(frozenset(sample_ids - short_episode_ids), ValidationMethod.HELD_OUT_EPISODES))

    distinct: list[ChargingHoldOut] = []
    seen: set[frozenset[int]] = set()
    for hold_out in hold_outs:
        if hold_out.sample_ids and hold_out.sample_ids not in seen:
            seen.add(hold_out.sample_ids)
            distinct.append(hold_out)
    return distinct


def _group_charges(episodes: Sequence[VacuumEpisode]) -> list[VacuumEpisode]:
    """Join charging episodes that only unidentified readings separate, as they are one physical charge."""
    charges: list[VacuumEpisode] = []
    previous: VacuumEpisode | None = None
    for episode in episodes:
        if episode.activity is None:
            continue
        if episode.activity == Activity.CHARGING:
            continues_charge = (
                previous is not None
                and previous.activity == Activity.CHARGING
                and previous.samples[0].recording_id == episode.samples[0].recording_id
            )
            if continues_charge:
                charges[-1].samples.extend(episode.samples)
            else:
                charges.append(VacuumEpisode(Activity.CHARGING, list(episode.samples)))
        previous = episode
    return charges


def _split_within_activities(
    samples: Sequence[RecordingSample],
    episodes: Sequence[VacuumEpisode],
    split: TrainingValidationSplit,
    activities: set[Activity],
    context: RecordingContext,
) -> TrainingValidationSplit:
    """Hold out contiguous blocks for activities without usable repeated cycles.

    Charging is split within battery buckets so a single rising charge provides
    both fitting and checking samples across its range. Keep bucket endpoints in
    training, and never bridge episode boundaries when selecting a block.
    """
    validation_ids = {id(sample) for sample in split.validation}
    battery = find_battery_feature(samples, context)
    for episode in episodes:
        if episode.activity not in activities or len(episode.samples) < MIN_EPISODE_SAMPLES:
            continue
        validation_ids.difference_update(id(sample) for sample in episode.samples)
        blocks: dict[int | None, list[RecordingSample]] = defaultdict(list)
        for sample in episode.samples:
            level = get_battery_level(sample, battery) if episode.activity == Activity.CHARGING else None
            key = level // CHARGING_BIN_WIDTH if level is not None else None
            blocks[key].append(sample)
        for block in blocks.values():
            count = max(2, len(block) // 3)
            start = (len(block) - count) // 2
            validation_ids.update(id(sample) for sample in block[max(0, start) : start + count])
    return TrainingValidationSplit(
        training=[sample for sample in samples if id(sample) not in validation_ids],
        validation=[sample for sample in samples if id(sample) in validation_ids],
        method=ValidationMethod.HELD_OUT_BLOCKS,
        signals=split.signals,
    )


def _try_split_by_recording(
    samples: Sequence[RecordingSample],
    grouped: Mapping[Activity, list[VacuumEpisode]],
    signals: list[ActivitySignal],
) -> TrainingValidationSplit | None:
    recordings = list(dict.fromkeys(sample.recording_id for sample in samples))
    if len(recordings) < 2:
        return None
    held_out = recordings[-1]
    durations: dict[int, float] = {}
    for episodes in grouped.values():
        for episode in episodes:
            durations.update(calculate_sample_durations(episode.samples, episode.samples))
    if not all(_is_represented_in_held_out_recording(items, held_out, durations) for items in grouped.values()):
        return None
    return TrainingValidationSplit(
        training=[sample for sample in samples if sample.recording_id != held_out],
        validation=[sample for sample in samples if sample.recording_id == held_out],
        method=ValidationMethod.HELD_OUT_RECORDING,
        signals=signals,
    )


def _split_by_episode(
    samples: Sequence[RecordingSample],
    episodes: Sequence[VacuumEpisode],
    grouped: Mapping[Activity, list[VacuumEpisode]],
    signals: list[ActivitySignal],
) -> TrainingValidationSplit:
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
    return TrainingValidationSplit(
        training=[sample for sample in samples if id(sample) not in validation_ids],
        validation=[sample for sample in samples if id(sample) in validation_ids],
        method=ValidationMethod.HELD_OUT_EPISODES,
        signals=signals,
    )


def _is_represented_in_held_out_recording(
    episodes: Sequence[VacuumEpisode], held_out: int, durations: Mapping[int, float]
) -> bool:
    """Whether training has this activity and the held-out recording covers enough of it."""
    held_out_episodes = [episode for episode in episodes if episode.samples[0].recording_id == held_out]
    training_episodes = [episode for episode in episodes if episode.samples[0].recording_id != held_out]
    if not held_out_episodes or not training_episodes:
        return False
    held_out_seconds = _calculate_episode_seconds(held_out_episodes, durations)
    total_seconds = held_out_seconds + _calculate_episode_seconds(training_episodes, durations)
    return held_out_seconds >= MIN_HELD_OUT_SHARE * total_seconds


def _calculate_episode_seconds(episodes: Sequence[VacuumEpisode], durations: Mapping[int, float]) -> float:
    return sum(durations.get(id(sample), 0.0) for episode in episodes for sample in episode.samples)
