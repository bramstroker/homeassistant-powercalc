from collections import Counter
from collections.abc import Sequence
import logging
import math
from pathlib import Path
from statistics import median

from measure.analyser.fixed import FixedStatesPowerStrategy
from measure.analyser.models import (
    ActivityReport,
    AnalysisCandidate,
    AnalysisMetrics,
    AnalysisStatus,
    EvaluatedCandidate,
    ProfileAnalysisStrategy,
    RecorderAnalysisResult,
    StrategyNotApplicable,
    TrainingValidationSplit,
    ValidationMethod,
)
from measure.analyser.recording import load_recordings, restore_recording_context
from measure.analyser.vacuum import VacuumCompositeCandidate, VacuumCompositeStrategy, split_vacuum_samples
from measure.analyser.vacuum_validation import build_activity_reports, find_credibility_failure
from measure.recording.models import RecordingContext, RecordingSample

MIN_VALIDATION_COVERAGE = 0.9
MIN_RELATIVE_MAE_IMPROVEMENT = 0.15
MIN_ABSOLUTE_MAE_IMPROVEMENT_W = 0.1
MIN_PREDICTION_RANGE_W = 0.1
MIN_SAMPLES_PER_MODEL_VALUE = 5

_LOGGER = logging.getLogger("measure")


class RecorderAnalyser:
    """Select the simplest credible profile model supported by a recording."""

    def __init__(self, strategies: Sequence[ProfileAnalysisStrategy] | None = None) -> None:
        self._default_strategies = strategies is None
        self.strategies: list[ProfileAnalysisStrategy] = (
            list(strategies) if strategies is not None else [FixedStatesPowerStrategy(), VacuumCompositeStrategy()]
        )

    def analyse(self, recording_path: Path | Sequence[Path], context: RecordingContext) -> RecorderAnalysisResult:
        loaded = load_recordings([recording_path] if isinstance(recording_path, Path) else recording_path)
        context = restore_recording_context(context, loaded.dataset.metadata)
        samples = loaded.dataset.samples
        if len(samples) < 10:
            return _build_insufficient_data_result(
                samples, loaded.warnings, "Record at least 10 valid samples across device states"
            )

        split = _split_analysis_samples(samples, context)
        if isinstance(split, StrategyNotApplicable):
            return _build_insufficient_data_result(samples, loaded.warnings, split.reason)
        baseline = _calculate_baseline_metrics(split.training, split.validation)
        evaluated: list[EvaluatedCandidate] = []
        reasons: list[str] = []
        reports: list[ActivityReport] = []
        for strategy in self._select_strategies(context):
            candidate = strategy.build_candidate(split.training, context, split.signals)
            if isinstance(candidate, StrategyNotApplicable):
                reasons.append(candidate.reason)
                _LOGGER.debug("Analyser strategy %s was not applicable: %s", strategy.strategy_id, candidate.reason)
                continue
            metrics = _evaluate(candidate, samples, split.validation)
            _LOGGER.debug("Analyser strategy %s produced %s", strategy.strategy_id, metrics.to_dict())
            reports = (
                build_activity_reports(candidate, samples, split.validation)
                if isinstance(candidate, VacuumCompositeCandidate)
                else []
            )
            evaluation = EvaluatedCandidate(candidate, metrics, reports)
            if (failure := _find_candidate_failure(evaluation, samples, baseline)) is None:
                evaluated.append(evaluation)
            else:
                reasons.append(failure)

        if not evaluated:
            reason = reasons[0] if reasons else "No analysis strategy could explain the recorded power"
            return _build_insufficient_data_result(samples, loaded.warnings, reason, split.method, reports)

        evaluation = _select_candidate(evaluated)
        selected = evaluation.candidate
        return RecorderAnalysisResult(
            status=AnalysisStatus.MODEL_READY,
            sample_count=len(samples),
            strategy=selected.strategy_id,
            feature=selected.feature,
            metrics=evaluation.metrics,
            model_config_fragment=selected.build_model_config_fragment(),
            standby_power=selected.standby_power,
            warnings=loaded.warnings,
            features=selected.features if isinstance(selected, VacuumCompositeCandidate) else [],
            validation_method=split.method,
            activity_reports=evaluation.activity_reports,
        )

    def _select_strategies(self, context: RecordingContext) -> list[ProfileAnalysisStrategy]:
        if not self._default_strategies:
            return self.strategies
        # Vacuum recipes require independent cycles and runtime signals; they
        # must not fall back to adjacent-sample fixed validation.
        is_vacuum = context.recipe == "vacuum_robot"
        return [strategy for strategy in self.strategies if (strategy.strategy_id == "vacuum_composite") == is_vacuum]


def _split_analysis_samples(
    samples: Sequence[RecordingSample], context: RecordingContext
) -> TrainingValidationSplit | StrategyNotApplicable:
    if context.recipe == "vacuum_robot":
        if any(sample.power < 0 for sample in samples):
            return StrategyNotApplicable("Vacuum power must be non-negative; check the meter or dummy-load correction")
        return split_vacuum_samples(samples, context)
    return _split_samples(samples)


def _find_candidate_failure(
    evaluation: EvaluatedCandidate,
    samples: Sequence[RecordingSample],
    baseline: AnalysisMetrics,
) -> str | None:
    candidate = evaluation.candidate
    metrics = evaluation.metrics
    if (failure := find_credibility_failure(evaluation.activity_reports)) is not None:
        return failure
    if not _has_minimum_support(candidate, samples):
        return f"{candidate.strategy_id} needs at least {MIN_SAMPLES_PER_MODEL_VALUE} samples for every value"
    prediction_range = _calculate_prediction_range(candidate, samples)
    return _find_model_credibility_failure(candidate.strategy_id, metrics, baseline, prediction_range)


def _split_samples(
    samples: Sequence[RecordingSample],
) -> TrainingValidationSplit:
    training = [sample for index, sample in enumerate(samples) if index % 5 != 4]
    validation = [sample for index, sample in enumerate(samples) if index % 5 == 4]
    return TrainingValidationSplit(training=training, validation=validation)


def _calculate_baseline_metrics(
    training: Sequence[RecordingSample],
    validation: Sequence[RecordingSample],
) -> AnalysisMetrics:
    estimate = median(sample.power for sample in training)
    errors = [estimate - sample.power for sample in validation]
    return _calculate_metrics(len(training) + len(validation), validation, errors, len(validation))


def _evaluate(
    candidate: AnalysisCandidate,
    samples: Sequence[RecordingSample],
    validation: Sequence[RecordingSample],
) -> AnalysisMetrics:
    errors = [
        estimate - sample.power for sample in validation if (estimate := candidate.estimate_power(sample)) is not None
    ]
    return _calculate_metrics(len(samples), validation, errors, len(errors))


def _calculate_metrics(
    sample_count: int,
    validation: Sequence[RecordingSample],
    errors: Sequence[float],
    covered: int,
) -> AnalysisMetrics:
    coverage = covered / len(validation) if validation else 0
    mae = sum(abs(error) for error in errors) / len(errors) if errors else math.inf
    rmse = math.sqrt(sum(error**2 for error in errors) / len(errors)) if errors else math.inf
    powers = [sample.power for sample in validation]
    power_range = max(powers) - min(powers) if powers else 0
    return AnalysisMetrics(sample_count, len(validation), coverage, mae, rmse, power_range)


def _calculate_prediction_range(candidate: AnalysisCandidate, samples: Sequence[RecordingSample]) -> float:
    predictions = [estimate for sample in samples if (estimate := candidate.estimate_power(sample)) is not None]
    return max(predictions) - min(predictions) if predictions else 0


def _find_model_credibility_failure(
    strategy_id: str,
    metrics: AnalysisMetrics,
    baseline: AnalysisMetrics,
    prediction_range: float,
) -> str | None:
    label = "The state-based profile" if strategy_id == "fixed_states_power" else f"The {strategy_id} profile"
    issues: list[str] = []
    if metrics.coverage < MIN_VALIDATION_COVERAGE:
        issues.append(
            f"it could estimate {metrics.coverage:.0%} of validation samples; "
            f"at least {MIN_VALIDATION_COVERAGE:.0%} is required",
        )
    if prediction_range < MIN_PREDICTION_RANGE_W:
        issues.append(
            f"its power estimates differed by only {prediction_range:.2f} W between recorded values; "
            f"at least {MIN_PREDICTION_RANGE_W:.2f} W is required",
        )
    improvement = baseline.mae_w - metrics.mae_w
    relative = improvement / baseline.mae_w if baseline.mae_w else 0
    if improvement < MIN_ABSOLUTE_MAE_IMPROVEMENT_W and relative < MIN_RELATIVE_MAE_IMPROVEMENT:
        issues.append(
            f"it reduced the typical validation difference from {baseline.mae_w:.2f} W to {metrics.mae_w:.2f} W "
            f"({relative:.0%}); at least {MIN_ABSOLUTE_MAE_IMPROVEMENT_W:.2f} W or "
            f"{MIN_RELATIVE_MAE_IMPROVEMENT:.0%} improvement is required",
        )
    return f"{label} was not reliable enough: {'; '.join(issues)}." if issues else None


def _has_minimum_support(candidate: AnalysisCandidate, samples: Sequence[RecordingSample]) -> bool:
    counts = Counter(
        key
        for sample in samples
        if (key := candidate.get_support_key(sample)) is not None and candidate.estimate_power(sample) is not None
    )
    return bool(counts) and min(counts.values()) >= MIN_SAMPLES_PER_MODEL_VALUE


def _select_candidate(
    candidates: Sequence[EvaluatedCandidate],
) -> EvaluatedCandidate:
    ordered = sorted(
        candidates,
        key=lambda item: (item.candidate.complexity, item.candidate.strategy_id, item.candidate.feature.identifier),
    )
    selected = ordered[0]
    for contender in ordered[1:]:
        improvement = selected.metrics.mae_w - contender.metrics.mae_w
        if contender.candidate.complexity == selected.candidate.complexity:
            if improvement > 0:
                selected = contender
            continue
        relative = improvement / selected.metrics.mae_w if selected.metrics.mae_w else 0
        if improvement >= MIN_ABSOLUTE_MAE_IMPROVEMENT_W and relative >= MIN_RELATIVE_MAE_IMPROVEMENT:
            selected = contender
    return selected


def _build_insufficient_data_result(
    samples: Sequence[RecordingSample],
    warnings: Sequence[str],
    reason: str,
    validation_method: ValidationMethod | None = None,
    reports: Sequence[ActivityReport] = (),
) -> RecorderAnalysisResult:
    return RecorderAnalysisResult(
        status=AnalysisStatus.INSUFFICIENT_DATA,
        sample_count=len(samples),
        reason=reason,
        warnings=list(warnings),
        validation_method=validation_method,
        activity_reports=list(reports),
    )
