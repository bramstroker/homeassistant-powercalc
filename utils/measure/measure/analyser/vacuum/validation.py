"""Activity-level checks so long idle periods cannot hide a bad short dock mode."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from measure.analyser.models import ActivityReport, EnergyMetrics
from measure.analyser.sample_intervals import calculate_sample_durations
from measure.analyser.vacuum.signals import Activity
from measure.analyser.vacuum.strategy import FixedBranch, VacuumCompositeCandidate, VacuumEpisode, group_vacuum_episodes
from measure.recording.models import RecordingSample

MAX_RELATIVE_ACTIVITY_ERROR = 0.2
MIN_ACTIVITY_ERROR_ALLOWANCE_W = 0.5
# Mirrors the 90% coverage rule: brief unavailable blips or transient states
# must not reject a recording whose activities are otherwise identified.
MAX_UNEXPLAINED_SHARE = 0.1


@dataclass
class _ActivityValidation:
    episodes: list[VacuumEpisode] = field(default_factory=list)
    samples: list[RecordingSample] = field(default_factory=list)
    predictions: dict[int, float] = field(default_factory=dict)

    def build_report(
        self, activity: Activity | None, recording: Sequence[RecordingSample], *, has_fixed_power: bool
    ) -> ActivityReport:
        transition_ids = {
            id(sample) for episode in self.episodes for sample in (episode.samples[0], episode.samples[-1])
        }
        errors: list[float] = []
        transition_errors: list[float] = []
        for sample in self.samples:
            power = self.predictions.get(id(sample))
            if power is None:
                continue
            error = abs(power - sample.power)
            errors.append(error)
            if id(sample) in transition_ids:
                transition_errors.append(error)
        return ActivityReport(
            activity=activity,
            sample_count=sum(len(episode.samples) for episode in self.episodes),
            episode_count=len(self.episodes),
            validation_count=len(self.samples),
            coverage=len(errors) / len(self.samples) if self.samples else 0,
            mae_w=sum(errors) / len(errors) if errors else None,
            transition_mae_w=sum(transition_errors) / len(transition_errors) if transition_errors else None,
            mean_power_w=sum(sample.power for sample in self.samples) / len(self.samples) if self.samples else 0,
            energy=_calculate_energy_metrics(recording, self.samples, self.predictions),
            has_fixed_power=has_fixed_power,
        )


def build_activity_reports(
    candidate: VacuumCompositeCandidate,
    samples: Sequence[RecordingSample],
    validation: Sequence[RecordingSample],
) -> list[ActivityReport]:
    """Group activities once and reuse each prediction for sample and energy errors."""
    grouped: dict[Activity | None, _ActivityValidation] = defaultdict(_ActivityValidation)
    for episode in group_vacuum_episodes(samples, candidate.signals):
        grouped[episode.activity].episodes.append(episode)
    for sample in validation:
        activity = candidate.get_support_key(sample)
        data = grouped[activity]
        data.samples.append(sample)
        power = candidate.estimate_activity_power(sample, activity)
        if power is not None:
            data.predictions[id(sample)] = power
    fixed_activities = {branch.activity for branch in candidate.branches if isinstance(branch, FixedBranch)}
    return [
        data.build_report(activity, samples, has_fixed_power=activity in fixed_activities)
        for activity, data in grouped.items()
    ]


def find_credibility_failure(reports: Sequence[ActivityReport]) -> str | None:
    total = sum(report.sample_count for report in reports)
    for report in reports:
        activity = report.activity
        if activity is None:
            if report.sample_count <= MAX_UNEXPLAINED_SHARE * total:
                continue
            return (
                f"{report.sample_count} of {total} samples match no known activity; "
                "record its runtime entities and repeat that cycle"
            )
        if (failure := _find_activity_failure(report)) is not None:
            return failure
    return None


def _find_activity_failure(report: ActivityReport) -> str | None:
    """Check coverage and the appropriate error metric for one identified activity."""
    activity = report.activity
    if report.coverage < 0.9 and not report.has_fixed_power:
        # A charging curve cannot estimate battery levels its training charges never reached.
        return (
            f"The {activity} model covers only {report.coverage:.0%} of its validation samples; "
            "record one continuous charge from a low battery through to full with mop drying off"
        )
    if report.coverage < 0.9:
        return (
            f"The vacuum profile cannot reliably identify {activity}; record its runtime entities and repeat that cycle"
        )
    if report.has_fixed_power:
        return _find_energy_failure(report)
    allowance = max(MIN_ACTIVITY_ERROR_ALLOWANCE_W, MAX_RELATIVE_ACTIVITY_ERROR * report.mean_power_w)
    if report.mae_w is None or report.mae_w > allowance:
        return (
            f"The {activity} validation error exceeds {allowance:.2f} W; record repeated, complete {activity} "
            "cycles and the entities that report this activity"
        )
    return None


def _find_energy_failure(report: ActivityReport) -> str | None:
    """Compare predicted and measured average power over the validated time of a fixed-power activity."""
    activity = report.activity
    energy = report.energy
    if energy.duration_seconds == 0:
        return f"The {activity} validation has no consecutive readings; record repeated, complete {activity} cycles"
    measured_w = energy.measured_wh * 3600 / energy.duration_seconds
    predicted_w = energy.predicted_wh * 3600 / energy.duration_seconds
    allowance = max(MIN_ACTIVITY_ERROR_ALLOWANCE_W, MAX_RELATIVE_ACTIVITY_ERROR * measured_w)
    if abs(predicted_w - measured_w) <= allowance:
        return None
    return (
        f"The {activity} validation predicts {predicted_w:.2f} W on average, but {measured_w:.2f} W was measured; "
        f"record repeated, complete {activity} cycles and the entities that report this activity"
    )


def _calculate_energy_metrics(
    samples: Sequence[RecordingSample],
    held_out: Sequence[RecordingSample],
    predictions: Mapping[int, float],
) -> EnergyMetrics:
    covered = [sample for sample in held_out if id(sample) in predictions]
    durations = calculate_sample_durations(samples, covered)
    measured = predicted = duration = 0.0
    for sample in covered:
        weight = durations.get(id(sample), 0.0)
        power = predictions[id(sample)]
        duration += weight
        measured += sample.power * weight / 3600
        predicted += power * weight / 3600
    return EnergyMetrics(
        duration_seconds=duration,
        measured_wh=measured,
        predicted_wh=predicted,
        bias_percent=100 * (predicted - measured) / measured if measured else None,
    )
