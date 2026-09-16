from collections import Counter
from collections.abc import Sequence
import logging
import math
from pathlib import Path
from statistics import median
from typing import TYPE_CHECKING

from measure.analyser.fixed import FixedStatesPowerStrategy
from measure.analyser.models import (
    ActivityReport,
    AnalysisCandidate,
    AnalysisContext,
    AnalysisMetrics,
    EntityRole,
    EvaluatedCandidate,
    ProfileAnalysisStrategy,
    RecordedEntity,
    RecorderAnalysisResult,
    RecordingSample,
    StrategyNotApplicable,
    TrainingValidationSplit,
    ValidationMethod,
)
from measure.analyser.recording import load_recordings, recording_context
from measure.analyser.vacuum import VacuumCompositeCandidate, VacuumCompositeStrategy, split_vacuum_samples
from measure.analyser.vacuum_validation import activity_reports, credibility_failure
from measure.request import RecorderMeasurementRequest, RecorderProfileRecipe

if TYPE_CHECKING:
    from measure.home_assistant_entities import EntityDescriptor

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

    def analyse(self, recording_path: Path | Sequence[Path], context: AnalysisContext) -> RecorderAnalysisResult:
        loaded = load_recordings([recording_path] if isinstance(recording_path, Path) else recording_path)
        context = recording_context(context, loaded.dataset.metadata)
        samples = loaded.dataset.samples
        if len(samples) < 10:
            return _insufficient(samples, loaded.warnings, "Record at least 10 valid samples across device states")

        split = _analysis_split(samples, context)
        if isinstance(split, StrategyNotApplicable):
            return _insufficient(samples, loaded.warnings, split.reason)
        baseline = _constant_metrics(split.training, split.validation)
        evaluated: list[EvaluatedCandidate] = []
        reasons: list[str] = []
        reports: list[ActivityReport] = []
        for strategy in self._strategies_for(context):
            candidate = strategy.build_candidate(split.training, context)
            if isinstance(candidate, StrategyNotApplicable):
                reasons.append(candidate.reason)
                _LOGGER.debug("Analyser strategy %s was not applicable: %s", strategy.strategy_id, candidate.reason)
                continue
            metrics = _evaluate(candidate, samples, split.validation)
            _LOGGER.debug("Analyser strategy %s produced %s", strategy.strategy_id, metrics.to_dict())
            reports = (
                activity_reports(candidate, samples, split.validation)
                if isinstance(candidate, VacuumCompositeCandidate)
                else []
            )
            evaluation = EvaluatedCandidate(candidate, metrics, reports)
            if (failure := _candidate_failure(evaluation, samples, baseline)) is None:
                evaluated.append(evaluation)
            else:
                reasons.append(failure)

        if not evaluated:
            reason = reasons[0] if reasons else "No analysis strategy could explain the recorded power"
            return _insufficient(samples, loaded.warnings, reason, split.method, reports)

        evaluation = _select_candidate(evaluated)
        selected = evaluation.candidate
        return RecorderAnalysisResult(
            status="model_ready",
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

    def _strategies_for(self, context: AnalysisContext) -> list[ProfileAnalysisStrategy]:
        if not self._default_strategies:
            return self.strategies
        # Vacuum recipes require independent cycles and runtime signals; they
        # must not fall back to adjacent-sample fixed validation.
        is_vacuum = context.recipe == "vacuum_robot"
        return [strategy for strategy in self.strategies if (strategy.strategy_id == "vacuum_composite") == is_vacuum]


def _analysis_split(
    samples: Sequence[RecordingSample], context: AnalysisContext
) -> TrainingValidationSplit | StrategyNotApplicable:
    if context.recipe == "vacuum_robot":
        if any(sample.power < 0 for sample in samples):
            return StrategyNotApplicable("Vacuum power must be non-negative; check the meter or dummy-load correction")
        return split_vacuum_samples(samples, context)
    return _split_samples(samples)


def _candidate_failure(
    evaluation: EvaluatedCandidate,
    samples: Sequence[RecordingSample],
    baseline: AnalysisMetrics,
) -> str | None:
    candidate = evaluation.candidate
    metrics = evaluation.metrics
    if (failure := credibility_failure(evaluation.activity_reports)) is not None:
        return failure
    if not _has_minimum_support(candidate, samples):
        return f"{candidate.strategy_id} needs at least {MIN_SAMPLES_PER_MODEL_VALUE} samples for every value"
    prediction_range = _prediction_range(candidate, samples)
    if not _credible(metrics, baseline, prediction_range):
        return _credibility_reason(candidate.strategy_id, metrics, baseline, prediction_range)
    return None


def analysis_context_for(
    request: RecorderMeasurementRequest,
    descriptors: Sequence[EntityDescriptor] = (),
) -> AnalysisContext:
    entity_ids = request.recorded_entity_ids
    if not entity_ids or request.profile_recipe is None:
        raise ValueError("A complex-profile recorder request is required for analysis")
    roles = dict.fromkeys(entity_ids, EntityRole.TRACKED)
    roles[entity_ids[0]] = EntityRole.PRIMARY
    if request.profile_recipe == RecorderProfileRecipe.VACUUM_ROBOT:
        roles[entity_ids[1]] = EntityRole.BATTERY
    by_id = {entity.entity_id: entity for entity in descriptors}

    primary = by_id.get(entity_ids[0])
    device_entities = [
        _recorded_entity(
            entity.entity_id, EntityRole.AVAILABLE if entity.disabled_by is None else EntityRole.DISABLED, entity
        )
        for entity in descriptors
        if primary is not None and primary.device_id is not None and entity.device_id == primary.device_id
    ]
    return AnalysisContext(
        recipe=request.profile_recipe.value,
        primary_entity_id=entity_ids[0],
        device_type="vacuum_robot" if request.profile_recipe == RecorderProfileRecipe.VACUUM_ROBOT else "generic_iot",
        entities=[_recorded_entity(entity_id, roles[entity_id], by_id.get(entity_id)) for entity_id in entity_ids],
        device_entities=device_entities,
    )


def _recorded_entity(entity_id: str, role: EntityRole, descriptor: EntityDescriptor | None) -> RecordedEntity:
    """Copy registry metadata, or retain just the identity when no descriptor exists."""
    if descriptor is None:
        return RecordedEntity(entity_id, entity_id.partition(".")[0], role)
    return RecordedEntity(
        entity_id=entity_id,
        domain=descriptor.domain,
        role=role,
        device_class=descriptor.device_class,
        integration=descriptor.integration,
        translation_key=descriptor.translation_key,
        device_id=descriptor.device_id,
        unit=descriptor.unit,
        disabled_by=descriptor.disabled_by,
        has_live_state=descriptor.has_live_state,
    )


def _split_samples(
    samples: Sequence[RecordingSample],
) -> TrainingValidationSplit:
    training = [sample for index, sample in enumerate(samples) if index % 5 != 4]
    validation = [sample for index, sample in enumerate(samples) if index % 5 == 4]
    return TrainingValidationSplit(training=training, validation=validation)


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
        key
        for sample in samples
        if (key := candidate.support_key(sample)) is not None and candidate.estimate_power(sample) is not None
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


def _insufficient(
    samples: Sequence[RecordingSample],
    warnings: Sequence[str],
    reason: str,
    validation_method: ValidationMethod | None = None,
    reports: Sequence[ActivityReport] = (),
) -> RecorderAnalysisResult:
    return RecorderAnalysisResult(
        status="insufficient_data",
        sample_count=len(samples),
        reason=reason,
        warnings=list(warnings),
        validation_method=validation_method,
        activity_reports=list(reports),
    )
