from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median

from measure.analyser.models import (
    AnalysisCandidate,
    AnalysisContext,
    FeatureReference,
    ModelConfigFragment,
    RecordingSample,
    ScalarStateValue,
    StrategyNotApplicable,
)

MIN_SAMPLES_PER_VALUE = 4
MAX_DISTINCT_VALUES = 20
_IGNORED_VALUES = {"unknown", "unavailable"}


@dataclass(frozen=True)
class FixedStatesPowerCandidate:
    feature: FeatureReference
    powers: Mapping[str, float]
    strategy_id: str = "fixed_states_power"

    @property
    def complexity(self) -> int:
        return len(self.powers)

    def estimate_power(self, sample: RecordingSample) -> float | None:
        value = self.feature.value(sample)
        if value is None:
            return None
        return self.powers.get(self.feature.model_key(value))

    def build_model_config_fragment(self) -> ModelConfigFragment:
        return ModelConfigFragment(
            calculation_strategy="fixed",
            configuration_key="fixed_config",
            configuration={"states_power": dict(self.powers)},
        )

    @property
    def standby_power(self) -> float | None:
        if self.feature.source != "state":
            return None
        power = self.powers.get("off")
        return power if power is not None and power >= 0.05 else None


class FixedStatesPowerStrategy:
    strategy_id = "fixed_states_power"

    def build_candidate(
        self,
        samples: Sequence[RecordingSample],
        context: AnalysisContext,
    ) -> AnalysisCandidate | StrategyNotApplicable:
        candidates = [
            candidate
            for feature in _features(samples, context.primary_entity_id)
            if (candidate := _fit_feature(samples, feature)) is not None
        ]
        if not candidates:
            return StrategyNotApplicable(
                f"No state or scalar attribute had 2-{MAX_DISTINCT_VALUES} usable values with at least "
                f"{MIN_SAMPLES_PER_VALUE} training samples per value",
            )
        return min(candidates, key=lambda candidate: (_training_mae(candidate, samples), candidate.feature.identifier))


def _features(samples: Sequence[RecordingSample], primary_entity_id: str) -> tuple[FeatureReference, ...]:
    attributes: set[str] = set()
    for sample in samples:
        entity = sample.entities.get(primary_entity_id)
        if entity is not None:
            attributes.update(entity.attributes)
    return (
        FeatureReference(primary_entity_id, "state"),
        *(FeatureReference(primary_entity_id, "attribute", attribute) for attribute in sorted(attributes)),
    )


def _fit_feature(
    samples: Sequence[RecordingSample],
    feature: FeatureReference,
) -> FixedStatesPowerCandidate | None:
    grouped: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        value = feature.value(sample)
        if value is None or not _usable(value):
            continue
        grouped[feature.model_key(value)].append(sample.power)
    if not 2 <= len(grouped) <= MAX_DISTINCT_VALUES:
        return None
    if any(len(powers) < MIN_SAMPLES_PER_VALUE for powers in grouped.values()):
        return None
    powers = {key: round(median(values), 2) for key, values in sorted(grouped.items())}
    return FixedStatesPowerCandidate(feature, powers)


def _usable(value: ScalarStateValue) -> bool:
    return not isinstance(value, str) or value.casefold() not in _IGNORED_VALUES


def _training_mae(candidate: FixedStatesPowerCandidate, samples: Sequence[RecordingSample]) -> float:
    errors = [
        abs(estimate - sample.power) for sample in samples if (estimate := candidate.estimate_power(sample)) is not None
    ]
    return sum(errors) / len(errors)
