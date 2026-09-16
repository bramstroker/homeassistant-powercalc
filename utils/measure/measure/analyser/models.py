from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import math
from typing import Literal, Protocol

type ScalarStateValue = str | bool | int | float

RECORDING_ANALYSIS_LABEL = "Recording analysis"


class EntityRole(StrEnum):
    PRIMARY = "primary"
    BATTERY = "battery"
    TRACKED = "tracked"
    AVAILABLE = "available"
    DISABLED = "disabled"


@dataclass(frozen=True)
class RecordedEntity:
    """Metadata describing an entity included in a recording."""

    entity_id: str
    domain: str
    role: str  # Known roles use EntityRole; recordings may contain other role names.
    device_class: str | None = None
    integration: str | None = None
    translation_key: str | None = None
    device_id: str | None = None
    unit: str | None = None
    disabled_by: str | None = None
    has_live_state: bool | None = None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "entity_id": self.entity_id,
            "domain": self.domain,
            "role": self.role,
        }
        for key in (
            "device_class",
            "integration",
            "translation_key",
            "device_id",
            "unit",
            "disabled_by",
            "has_live_state",
        ):
            item = getattr(self, key)
            if item is not None:
                value[key] = item
        return value


@dataclass(frozen=True)
class RecordedEntityState:
    state: str
    attributes: Mapping[str, object]


@dataclass(frozen=True)
class RecordingSample:
    elapsed_seconds: float
    power: float
    entities: Mapping[str, RecordedEntityState]
    recording_id: int = 0


class ValidationMethod(StrEnum):
    HELD_OUT_RECORDING = "held_out_recording"
    HELD_OUT_EPISODES = "held_out_episodes"


@dataclass(frozen=True)
class TrainingValidationSplit:
    """Samples used to fit a model and independently validate it."""

    training: list[RecordingSample]
    validation: list[RecordingSample]
    method: ValidationMethod | None = None


@dataclass(frozen=True)
class AnalysisContext:
    recipe: str
    primary_entity_id: str
    device_type: str
    entities: list[RecordedEntity]
    device_entities: list[RecordedEntity] = field(default_factory=list)

    def metadata_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "record_type": "metadata",
            "format_version": 1,
            "recipe": self.recipe,
            "primary_entity_id": self.primary_entity_id,
            "entities": [entity.to_dict() for entity in self.entities],
        }
        if self.device_entities:
            record["device_entities"] = [entity.to_dict() for entity in self.device_entities]
        return record


@dataclass(frozen=True)
class RecordingDataset:
    samples: list[RecordingSample]
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True)
class LoadedRecording:
    dataset: RecordingDataset
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FeatureReference:
    entity_id: str
    source: Literal["state", "attribute"]
    attribute: str | None = None

    @property
    def identifier(self) -> str:
        if self.source == "state":
            return f"{self.entity_id}.state"
        return f"{self.entity_id}.attributes.{self.attribute}"

    def value(self, sample: RecordingSample) -> ScalarStateValue | None:
        entity = sample.entities.get(self.entity_id)
        if entity is None:
            return None
        value: object = entity.state if self.source == "state" else entity.attributes.get(str(self.attribute))
        if isinstance(value, bool | int | str):
            return value
        if isinstance(value, float) and math.isfinite(value):
            return value
        return None

    def model_key(self, value: ScalarStateValue) -> str:
        rendered = str(value)
        return rendered if self.source == "state" else f"{self.attribute}|{rendered}"


@dataclass(frozen=True)
class ModelConfigFragment:
    calculation_strategy: str
    configuration_key: str
    configuration: Mapping[str, object] | Sequence[Mapping[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "calculation_strategy": self.calculation_strategy,
            self.configuration_key: dict(self.configuration)
            if isinstance(self.configuration, Mapping)
            else [dict(branch) for branch in self.configuration],
        }


class AnalysisCandidate(Protocol):
    @property
    def strategy_id(self) -> str: ...

    @property
    def feature(self) -> FeatureReference: ...

    @property
    def features(self) -> list[FeatureReference]: ...

    def support_key(self, sample: RecordingSample) -> str | None: ...

    @property
    def complexity(self) -> int: ...

    def estimate_power(self, sample: RecordingSample) -> float | None: ...

    def build_model_config_fragment(self) -> ModelConfigFragment: ...

    @property
    def standby_power(self) -> float | None: ...


@dataclass(frozen=True)
class StrategyNotApplicable:
    reason: str


class ProfileAnalysisStrategy(Protocol):
    @property
    def strategy_id(self) -> str: ...

    def build_candidate(
        self,
        samples: Sequence[RecordingSample],
        context: AnalysisContext,
    ) -> AnalysisCandidate | StrategyNotApplicable: ...


@dataclass(frozen=True)
class AnalysisMetrics:
    sample_count: int
    validation_count: int
    coverage: float
    mae_w: float
    rmse_w: float
    power_range_w: float

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_count": self.sample_count,
            "validation_count": self.validation_count,
            "coverage": round(self.coverage, 4),
            "mae_w": round(self.mae_w, 3),
            "rmse_w": round(self.rmse_w, 3),
            "power_range_w": round(self.power_range_w, 3),
        }


@dataclass(frozen=True)
class EnergyMetrics:
    duration_seconds: float
    measured_wh: float
    predicted_wh: float
    bias_percent: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "energy_duration_seconds": self.duration_seconds,
            "measured_energy_wh": self.measured_wh,
            "predicted_energy_wh": self.predicted_wh,
            "energy_bias_percent": self.bias_percent,
        }


@dataclass(frozen=True)
class ActivityReport:
    """Validation results for one vacuum activity, or unexplained samples."""

    activity: str
    sample_count: int
    episode_count: int
    validation_count: int
    coverage: float
    mae_w: float | None
    transition_mae_w: float | None
    mean_power_w: float
    energy: EnergyMetrics

    def to_dict(self) -> dict[str, object]:
        return {
            "activity": self.activity,
            "sample_count": self.sample_count,
            "episode_count": self.episode_count,
            "validation_count": self.validation_count,
            "coverage": self.coverage,
            "mae_w": self.mae_w,
            "transition_mae_w": self.transition_mae_w,
            "mean_power_w": self.mean_power_w,
            **self.energy.to_dict(),
        }


@dataclass(frozen=True)
class EvaluatedCandidate:
    candidate: AnalysisCandidate
    metrics: AnalysisMetrics
    activity_reports: list[ActivityReport] = field(default_factory=list)


@dataclass(frozen=True)
class RecorderAnalysisResult:
    status: Literal["model_ready", "insufficient_data"]
    sample_count: int
    reason: str | None = None
    strategy: str | None = None
    feature: FeatureReference | None = None
    metrics: AnalysisMetrics | None = None
    model_config_fragment: ModelConfigFragment | None = None
    standby_power: float | None = None
    warnings: list[str] = field(default_factory=list)
    features: list[FeatureReference] = field(default_factory=list)
    validation_method: ValidationMethod | None = None
    activity_reports: list[ActivityReport] = field(default_factory=list)

    @property
    def model_ready(self) -> bool:
        return self.status == "model_ready" and self.model_config_fragment is not None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": 1,
            "status": self.status,
            "sample_count": self.sample_count,
        }
        if self.reason is not None:
            value["reason"] = self.reason
        if self.strategy is not None:
            value["strategy"] = self.strategy
        if self.feature is not None:
            value["feature"] = self.feature.identifier
        if self.metrics is not None:
            value["metrics"] = self.metrics.to_dict()
        if self.model_config_fragment is not None:
            value["model_config_fragment"] = self.model_config_fragment.to_dict()
        if self.standby_power is not None:
            value["standby_power"] = self.standby_power
        if self.warnings:
            value["warnings"] = list(self.warnings)
        value.update(self._validation_details())
        return value

    def _validation_details(self) -> dict[str, object]:
        details: dict[str, object] = {}
        if self.features:
            details["features"] = [feature.identifier for feature in self.features]
        if self.validation_method is not None:
            details["validation_method"] = self.validation_method.value
        if self.activity_reports:
            details["activities"] = [report.to_dict() for report in self.activity_reports]
        return details

    def summary(self) -> dict[str, str]:
        if not self.model_ready:
            summary = {RECORDING_ANALYSIS_LABEL: "More data needed"}
            if self.reason is not None:
                summary["Recording analysis reason"] = self.reason
            return summary
        assert self.feature is not None
        assert self.metrics is not None
        assert self.model_config_fragment is not None
        if self.model_config_fragment.calculation_strategy == "composite":
            return {
                RECORDING_ANALYSIS_LABEL: "Composite vacuum profile created",
                "Analysed inputs": ", ".join(feature.identifier for feature in self.features),
                "Validation MAE": f"{self.metrics.mae_w:.2f} W",
                "Validation coverage": f"{self.metrics.coverage:.0%}",
                "Validation method": self.validation_method.value if self.validation_method else "held-out episodes",
                "Recorded activities": ", ".join(report.activity for report in self.activity_reports),
            }
        fixed_config = self.model_config_fragment.configuration
        profile_type = "Fixed power" if "power" in fixed_config else "Fixed states_power"
        return {
            RECORDING_ANALYSIS_LABEL: f"{profile_type} profile created",
            "Analysed feature": self.feature.identifier,
            "Validation MAE": f"{self.metrics.mae_w:.2f} W",
            "Validation coverage": f"{self.metrics.coverage:.0%}",
        }
