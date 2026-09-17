"""Activity-level checks so long idle periods cannot hide a bad short dock mode."""

from collections.abc import Sequence
from itertools import pairwise

from measure.analyser.models import ActivityReport, EnergyMetrics, RecordingSample
from measure.analyser.vacuum import VacuumCompositeCandidate, vacuum_episodes

MAX_RELATIVE_ACTIVITY_MAE = 0.2
MIN_ACTIVITY_MAE_ALLOWANCE_W = 0.5
# Mirrors the 90% coverage rule: brief unavailable blips or transient states
# must not reject a recording whose activities are otherwise identified.
MAX_UNEXPLAINED_SHARE = 0.1


def activity_reports(
    candidate: VacuumCompositeCandidate,
    samples: Sequence[RecordingSample],
    validation: Sequence[RecordingSample],
) -> tuple[ActivityReport, ...]:
    episodes = vacuum_episodes(samples, candidate.signals)
    activities = tuple(dict.fromkeys(episode.activity for episode in episodes))
    transition_ids = {id(sample) for episode in episodes for sample in (episode.samples[0], episode.samples[-1])}
    reports: list[ActivityReport] = []
    for activity in activities:
        all_samples = [sample for sample in samples if candidate.support_key(sample) == activity]
        held_out = [sample for sample in validation if candidate.support_key(sample) == activity]
        errors = _prediction_errors(candidate, held_out)
        transition_errors = _prediction_errors(
            candidate, [sample for sample in held_out if id(sample) in transition_ids]
        )
        reports.append(
            ActivityReport(
                activity=activity.value if activity is not None else "unexplained",
                sample_count=len(all_samples),
                episode_count=sum(episode.activity == activity for episode in episodes),
                validation_count=len(held_out),
                coverage=round(len(errors) / len(held_out), 4) if held_out else 0,
                mae_w=round(sum(errors) / len(errors), 3) if errors else None,
                transition_mae_w=round(sum(transition_errors) / len(transition_errors), 3)
                if transition_errors
                else None,
                mean_power_w=sum(sample.power for sample in held_out) / len(held_out) if held_out else 0,
                energy=_energy(candidate, samples, held_out),
            )
        )
    return tuple(reports)


def _prediction_errors(candidate: VacuumCompositeCandidate, samples: Sequence[RecordingSample]) -> list[float]:
    return [abs(power - sample.power) for sample in samples if (power := candidate.estimate_power(sample)) is not None]


def credibility_failure(reports: Sequence[ActivityReport]) -> str | None:
    total = sum(report.sample_count for report in reports)
    for report in reports:
        activity = report.activity
        if activity == "unexplained":
            if report.sample_count <= MAX_UNEXPLAINED_SHARE * total:
                continue
            return (
                f"{report.sample_count} of {total} samples match no known activity; "
                "record its runtime entities and repeat that cycle"
            )
        if report.coverage < 0.9:
            return (
                f"The vacuum profile cannot reliably identify {activity}; "
                "record its runtime entities and repeat that cycle"
            )
        allowance = max(MIN_ACTIVITY_MAE_ALLOWANCE_W, MAX_RELATIVE_ACTIVITY_MAE * report.mean_power_w)
        if report.mae_w is None or report.mae_w > allowance:
            return (
                f"The {activity} validation error exceeds {allowance:.2f} W; record repeated isolated cycles and "
                "active charging/washing/drying entities (settings switches are not activity signals)"
            )
    return None


def _energy(
    candidate: VacuumCompositeCandidate,
    samples: Sequence[RecordingSample],
    held_out: Sequence[RecordingSample],
) -> EnergyMetrics:
    selected = {id(sample) for sample in held_out}
    measured = predicted = duration = 0.0
    for left, right in pairwise(samples):
        if id(left) not in selected or id(right) not in selected or left.recording_id != right.recording_id:
            continue
        delta = right.elapsed_seconds - left.elapsed_seconds
        first, second = candidate.estimate_power(left), candidate.estimate_power(right)
        if not 0 < delta <= 30 or first is None or second is None:
            continue
        duration += delta
        measured += (left.power + right.power) / 2 * delta / 3600
        predicted += (first + second) / 2 * delta / 3600
    return EnergyMetrics(
        duration_seconds=round(duration, 3),
        measured_wh=round(measured, 4),
        predicted_wh=round(predicted, 4),
        bias_percent=round(100 * (predicted - measured) / measured, 2) if measured else None,
    )
