from collections import Counter
from collections.abc import Sequence
import logging
import math
from pathlib import Path
from statistics import median

from measure.analyser.fixed import FixedStatesPowerStrategy
from measure.analyser.models import (
    AnalysisCandidate,
    AnalysisContext,
    AnalysisMetrics,
    ProfileAnalysisStrategy,
    RecordedEntity,
    RecorderAnalysisResult,
    RecordingSample,
    StrategyNotApplicable,
)
from measure.analyser.recording import load_recording
from measure.request import RecorderMeasurementRequest, RecorderProfileRecipe

MIN_VALIDATION_COVERAGE = 0.9
MIN_RELATIVE_MAE_IMPROVEMENT = 0.15
MIN_ABSOLUTE_MAE_IMPROVEMENT_W = 0.1
MIN_PREDICTION_RANGE_W = 0.1
MIN_SAMPLES_PER_MODEL_VALUE = 5

_LOGGER = logging.getLogger("measure")


class RecorderAnalyser:
    """Select the simplest credible profile model supported by a recording."""

    def __init__(self, strategies: Sequence[ProfileAnalysisStrategy] | None = None) -> None:
        self.strategies = tuple(strategies) if strategies is not None else (FixedStatesPowerStrategy(),)

    def analyse(self, recording_path: Path, context: AnalysisContext) -> RecorderAnalysisResult:
        loaded = load_recording(recording_path)
        samples = loaded.dataset.samples
        if len(samples) < 10:
            return _insufficient(samples, loaded.warnings, "Record at least 10 valid samples across device states")

        training, validation = _split_samples(samples)
        baseline = _constant_metrics(training, validation)
        evaluated: list[tuple[AnalysisCandidate, AnalysisMetrics]] = []
        reasons: list[str] = []
        for strategy in self.strategies:
            candidate = strategy.build_candidate(training, context)
            if isinstance(candidate, StrategyNotApplicable):
                reasons.append(candidate.reason)
                _LOGGER.debug("Analyser strategy %s was not applicable: %s", strategy.strategy_id, candidate.reason)
                continue
            metrics = _evaluate(candidate, samples, validation)
            prediction_range = _prediction_range(candidate, samples)
            _LOGGER.debug("Analyser strategy %s produced %s", strategy.strategy_id, metrics.to_dict())
            if not _has_minimum_support(candidate, samples):
                reasons.append(
                    f"{strategy.strategy_id} needs at least {MIN_SAMPLES_PER_MODEL_VALUE} samples for every value",
                )
            elif _credible(metrics, baseline, prediction_range):
                evaluated.append((candidate, metrics))
            else:
                reasons.append(_credibility_reason(strategy.strategy_id, metrics, baseline, prediction_range))

        if not evaluated:
            reason = reasons[0] if reasons else "No analysis strategy could explain the recorded power"
            return _insufficient(samples, loaded.warnings, reason)

        selected, metrics = _select_candidate(evaluated)
        return RecorderAnalysisResult(
            status="model_ready",
            sample_count=len(samples),
            strategy=selected.strategy_id,
            feature=selected.feature,
            metrics=metrics,
            model_config_fragment=selected.build_model_config_fragment(),
            standby_power=selected.standby_power,
            warnings=loaded.warnings,
        )


def analysis_context_for(request: RecorderMeasurementRequest) -> AnalysisContext:
    entity_ids = request.recorded_entity_ids
    if not entity_ids or request.profile_recipe is None:
        raise ValueError("A complex-profile recorder request is required for analysis")
    roles = ["primary", *("tracked" for _ in entity_ids[1:])]
    if request.profile_recipe == RecorderProfileRecipe.VACUUM_ROBOT:
        roles[1] = "battery"
    return AnalysisContext(
        recipe=request.profile_recipe.value,
        primary_entity_id=entity_ids[0],
        device_type="vacuum_robot" if request.profile_recipe == RecorderProfileRecipe.VACUUM_ROBOT else "generic_iot",
        entities=tuple(
            RecordedEntity(entity_id, entity_id.partition(".")[0], role)
            for entity_id, role in zip(entity_ids, roles, strict=True)
        ),
    )


def _split_samples(
    samples: Sequence[RecordingSample],
) -> tuple[tuple[RecordingSample, ...], tuple[RecordingSample, ...]]:
    training = tuple(sample for index, sample in enumerate(samples) if index % 5 != 4)
    validation = tuple(sample for index, sample in enumerate(samples) if index % 5 == 4)
    return training, validation


def _constant_metrics(
    training: Sequence[RecordingSample],
    validation: Sequence[RecordingSample],
) -> AnalysisMetrics:
    estimate = median(sample.power for sample in training)
    errors = [estimate - sample.power for sample in validation]
    return _metrics(len(training) + len(validation), validation, errors, len(validation))


def _evaluate(
    candidate: AnalysisCandidate,
    samples: Sequence[RecordingSample],
    validation: Sequence[RecordingSample],
) -> AnalysisMetrics:
    errors = [
        estimate - sample.power for sample in validation if (estimate := candidate.estimate_power(sample)) is not None
    ]
    return _metrics(len(samples), validation, errors, len(errors))


def _metrics(
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


def _credible(metrics: AnalysisMetrics, baseline: AnalysisMetrics, prediction_range: float) -> bool:
    improvement = baseline.mae_w - metrics.mae_w
    relative = improvement / baseline.mae_w if baseline.mae_w else 0
    return (
        metrics.coverage >= MIN_VALIDATION_COVERAGE
        and prediction_range >= MIN_PREDICTION_RANGE_W
        and (improvement >= MIN_ABSOLUTE_MAE_IMPROVEMENT_W or relative >= MIN_RELATIVE_MAE_IMPROVEMENT)
    )


def _prediction_range(candidate: AnalysisCandidate, samples: Sequence[RecordingSample]) -> float:
    predictions = [estimate for sample in samples if (estimate := candidate.estimate_power(sample)) is not None]
    return max(predictions) - min(predictions) if predictions else 0


def _credibility_reason(
    strategy_id: str,
    metrics: AnalysisMetrics,
    baseline: AnalysisMetrics,
    prediction_range: float,
) -> str:
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
    return f"{label} was not reliable enough: {'; '.join(issues)}."


def _has_minimum_support(candidate: AnalysisCandidate, samples: Sequence[RecordingSample]) -> bool:
    counts = Counter(
        candidate.feature.model_key(value)
        for sample in samples
        if (value := candidate.feature.value(sample)) is not None and candidate.estimate_power(sample) is not None
    )
    return bool(counts) and min(counts.values()) >= MIN_SAMPLES_PER_MODEL_VALUE


def _select_candidate(
    candidates: Sequence[tuple[AnalysisCandidate, AnalysisMetrics]],
) -> tuple[AnalysisCandidate, AnalysisMetrics]:
    ordered = sorted(candidates, key=lambda item: (item[0].complexity, item[0].strategy_id, item[0].feature.identifier))
    selected = ordered[0]
    for candidate in ordered[1:]:
        improvement = selected[1].mae_w - candidate[1].mae_w
        if candidate[0].complexity == selected[0].complexity:
            if improvement > 0:
                selected = candidate
            continue
        relative = improvement / selected[1].mae_w if selected[1].mae_w else 0
        if improvement >= MIN_ABSOLUTE_MAE_IMPROVEMENT_W and relative >= MIN_RELATIVE_MAE_IMPROVEMENT:
            selected = candidate
    return selected


def _insufficient(
    samples: Sequence[RecordingSample],
    warnings: tuple[str, ...],
    reason: str,
) -> RecorderAnalysisResult:
    return RecorderAnalysisResult(
        status="insufficient_data",
        sample_count=len(samples),
        reason=reason,
        warnings=warnings,
    )
