from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median

from measure.analyser.entity_references import resolve_portable_entity
from measure.analyser.models import (
    AnalysisCandidate,
    FeatureReference,
    FeatureSource,
    ModelConfigFragment,
    ProfileAnalysisStrategy,
    ScalarStateValue,
    StrategyNotApplicable,
)
from measure.analyser.vacuum.signals import ActivitySignal
from measure.recording.models import RecordingContext, RecordingSample

MIN_SAMPLES_PER_VALUE = 5
MAX_DISTINCT_VALUES = 20
_IGNORED_VALUES = {"unknown", "unavailable"}


@dataclass(frozen=True)
class FixedStatesPowerCandidate:
    feature: FeatureReference
    powers: Mapping[str, float]
    strategy_id: str = "fixed_states_power"
    source_entity: str | None = None

    @property
    def features(self) -> list[FeatureReference]:
        return [self.feature]

    def get_support_key(self, sample: RecordingSample) -> str | None:
        value = self.feature.get_value(sample)
        return self.feature.format_model_key(value) if value is not None else None

    @property
    def complexity(self) -> int:
        return len(self.powers)

    def estimate_power(self, sample: RecordingSample) -> float | None:
        value = self.feature.get_value(sample)
        if value is None:
            return None
        return self.powers.get(self.feature.format_model_key(value))

    def build_model_config_fragment(self) -> ModelConfigFragment:
        if self.source_entity is not None:
            # Keep the primary source, including its off state. Conditions track the
            # secondary entity without treating its "off" value as zero consumption.
            strategies = [
                {
                    "condition": {"condition": "state", "entity_id": self.source_entity, "state": state},
                    "fixed": {"power": power, "states_power": {"off": power}},
                }
                for state, power in self.powers.items()
            ]
            return ModelConfigFragment(
                "composite", "composite_config", {"mode": "stop_at_first", "strategies": strategies}
            )
        configuration: dict[str, object]
        if self.feature.source == FeatureSource.STATE and set(self.powers) == {"off", "on"}:
            configuration = {"power": self.powers["on"]}
        else:
            configuration = {"states_power": dict(self.powers)}
        return ModelConfigFragment(
            calculation_strategy="fixed",
            configuration_key="fixed_config",
            configuration=configuration,
        )

    @property
    def standby_power(self) -> float | None:
        if self.source_entity is not None or self.feature.source != FeatureSource.STATE:
            return None
        power = self.powers.get("off")
        return power if power is not None and power >= 0.05 else None


class FixedStatesPowerStrategy(ProfileAnalysisStrategy):
    strategy_id = "fixed_states_power"

    def build_candidates(
        self,
        samples: Sequence[RecordingSample],
        context: RecordingContext,
        signals: Sequence[ActivitySignal],  # Unused: a fixed profile resolves no vacuum activities.
        *,
        recording_samples: Sequence[RecordingSample] | None = None,
    ) -> list[AnalysisCandidate] | StrategyNotApplicable:
        candidates: list[AnalysisCandidate] = [
            candidate
            for feature in _collect_features(samples, context.primary_entity_id)
            if (candidate := _fit_feature(samples, feature)) is not None
        ]
        for entity in context.entities:
            if entity.entity_id == context.primary_entity_id:
                continue
            reference = resolve_portable_entity(entity.entity_id, context)
            if reference is None:
                continue
            feature = FeatureReference(entity.entity_id, FeatureSource.STATE)
            if (candidate := _fit_feature(samples, feature, reference)) is not None:
                candidates.append(candidate)
        if not candidates:
            return StrategyNotApplicable(
                f"No state or scalar attribute had 2-{MAX_DISTINCT_VALUES} usable values with at least "
                f"{MIN_SAMPLES_PER_VALUE} training samples per value. Secondary states also need an unambiguous "
                "portable entity reference.",
            )
        return candidates


def _collect_features(samples: Sequence[RecordingSample], primary_entity_id: str) -> list[FeatureReference]:
    attributes: set[str] = set()
    for sample in samples:
        entity = sample.entities.get(primary_entity_id)
        if entity is not None:
            attributes.update(entity.attributes)
    return [
        FeatureReference(primary_entity_id, FeatureSource.STATE),
        *(FeatureReference(primary_entity_id, FeatureSource.ATTRIBUTE, attribute) for attribute in sorted(attributes)),
    ]


def _fit_feature(
    samples: Sequence[RecordingSample],
    feature: FeatureReference,
    source_entity: str | None = None,
) -> FixedStatesPowerCandidate | None:
    grouped: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        value = feature.get_value(sample)
        if value is None or not _is_usable(value):
            continue
        grouped[feature.format_model_key(value)].append(sample.power)
    if not 2 <= len(grouped) <= MAX_DISTINCT_VALUES:
        return None
    if any(len(powers) < MIN_SAMPLES_PER_VALUE for powers in grouped.values()):
        return None
    powers = {key: round(median(values), 2) for key, values in sorted(grouped.items())}
    return FixedStatesPowerCandidate(feature, powers, source_entity=source_entity)


def _is_usable(value: ScalarStateValue) -> bool:
    return not isinstance(value, str) or value.casefold() not in _IGNORED_VALUES
