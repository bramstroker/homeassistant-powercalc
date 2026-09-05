from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Literal, Protocol

type ScalarStateValue = str | bool | int | float


@dataclass(frozen=True)
class RecordedEntity:
    """Metadata describing an entity included in a recording."""

    entity_id: str
    domain: str
    role: str
    device_class: str | None = None
    integration: str | None = None
    translation_key: str | None = None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "entity_id": self.entity_id,
            "domain": self.domain,
            "role": self.role,
        }
        for key in ("device_class", "integration", "translation_key"):
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


@dataclass(frozen=True)
class AnalysisContext:
    recipe: str
    primary_entity_id: str
    device_type: str
    entities: tuple[RecordedEntity, ...]

    def metadata_record(self) -> dict[str, object]:
        return {
            "record_type": "metadata",
            "format_version": 1,
            "recipe": self.recipe,
            "primary_entity_id": self.primary_entity_id,
            "entities": [entity.to_dict() for entity in self.entities],
        }


@dataclass(frozen=True)
class RecordingDataset:
    samples: tuple[RecordingSample, ...]
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True)
class LoadedRecording:
    dataset: RecordingDataset
    warnings: tuple[str, ...] = ()


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
    configuration: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "calculation_strategy": self.calculation_strategy,
            self.configuration_key: dict(self.configuration),
        }


class AnalysisCandidate(Protocol):
    @property
    def strategy_id(self) -> str: ...

    @property
    def feature(self) -> FeatureReference: ...

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
class RecorderAnalysisResult:
    status: Literal["model_ready", "insufficient_data"]
    sample_count: int
    reason: str | None = None
    strategy: str | None = None
    feature: FeatureReference | None = None
    metrics: AnalysisMetrics | None = None
    model_config_fragment: ModelConfigFragment | None = None
    standby_power: float | None = None
    warnings: tuple[str, ...] = ()

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
        return value

    def summary(self) -> dict[str, str]:
        if not self.model_ready:
            summary = {"Recording analysis": "More data needed"}
            if self.reason is not None:
                summary["Recording analysis reason"] = self.reason
            return summary
        assert self.feature is not None
        assert self.metrics is not None
        assert self.model_config_fragment is not None
        fixed_config = self.model_config_fragment.configuration
        profile_type = "Fixed power" if "power" in fixed_config else "Fixed states_power"
        return {
            "Recording analysis": f"{profile_type} profile created",
            "Analysed feature": self.feature.identifier,
            "Validation MAE": f"{self.metrics.mae_w:.2f} W",
            "Validation coverage": f"{self.metrics.coverage:.0%}",
        }
