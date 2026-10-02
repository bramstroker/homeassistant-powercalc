from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import math
from typing import TYPE_CHECKING, Protocol

from measure.recording.models import RecordingContext, RecordingSample

if TYPE_CHECKING:
    from measure.analyser.vacuum.signals import ActivitySignal

type ScalarStateValue = str | bool | int | float

RECORDING_ANALYSIS_LABEL = "Recording analysis"
# The bucket for samples matching no activity. Not a mode the profile covers.
UNEXPLAINED_ACTIVITY = "unexplained"


class Activity(StrEnum):
    AUTO_EMPTYING = "auto_emptying"
    STATION_CLEANING = "station_cleaning"
    WASHING = "washing"
    DRYING = "drying"
    CHARGING = "charging"
    SLEEPING = "sleeping"
    COMPLETED = "completed"
    DOCKED = "docked"
    AWAY = "away"


class FeatureSource(StrEnum):
    STATE = "state"
    ATTRIBUTE = "attribute"


class AnalysisStatus(StrEnum):
    MODEL_READY = "model_ready"
    INSUFFICIENT_DATA = "insufficient_data"


class ValidationMethod(StrEnum):
    HELD_OUT_RECORDING = "held_out_recording"
    HELD_OUT_EPISODES = "held_out_episodes"
    HELD_OUT_BLOCKS = "held_out_blocks"


@dataclass(frozen=True)
class TrainingValidationSplit:
    """Separate samples used to fit a model and check its predictions.

    The signals travel with the split because they were discovered over every sample to
    establish its episode coverage. A strategy that rediscovered them from the training
    half alone would judge validation samples against a narrower vocabulary than the one
    the split was accepted under, and report the difference as unexplained.
    """

    training: list[RecordingSample]
    validation: list[RecordingSample]
    method: ValidationMethod | None = None
    signals: Sequence[ActivitySignal] = ()


@dataclass(frozen=True)
class FeatureReference:
    entity_id: str
    source: FeatureSource
    attribute: str | None = None

    @property
    def identifier(self) -> str:
        if self.source == FeatureSource.STATE:
            return f"{self.entity_id}.state"
        return f"{self.entity_id}.attributes.{self.attribute}"

    def get_value(self, sample: RecordingSample) -> ScalarStateValue | None:
        entity = sample.entities.get(self.entity_id)
        if entity is None:
            return None
        value: object = (
            entity.state if self.source == FeatureSource.STATE else entity.attributes.get(str(self.attribute))
        )
        if isinstance(value, bool | int | str):
            return value
        if isinstance(value, float) and math.isfinite(value):
            return value
        return None

    def format_model_key(self, value: ScalarStateValue) -> str:
        rendered = str(value)
        return rendered if self.source == FeatureSource.STATE else f"{self.attribute}|{rendered}"


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
    def features(self) -> list[FeatureReference]: ...

    def get_support_key(self, sample: RecordingSample) -> str | None: ...

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
    """Fit training samples, optionally using the full recording to preserve interval boundaries."""

    @property
    def strategy_id(self) -> str: ...

    def build_candidates(
        self,
        samples: Sequence[RecordingSample],
        context: RecordingContext,
        signals: Sequence[ActivitySignal],
        *,
        recording_samples: Sequence[RecordingSample] | None = None,
    ) -> list[AnalysisCandidate] | StrategyNotApplicable: ...


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
            "energy_duration_seconds": round(self.duration_seconds, 3),
            "measured_energy_wh": round(self.measured_wh, 4),
            "predicted_energy_wh": round(self.predicted_wh, 4),
            "energy_bias_percent": round(self.bias_percent, 2) if self.bias_percent is not None else None,
        }


@dataclass(frozen=True)
class ActivityReport:
    """Validation results for one vacuum activity, or unexplained samples."""

    activity: Activity | None
    sample_count: int
    episode_count: int
    validation_count: int
    coverage: float
    mae_w: float | None
    transition_mae_w: float | None
    mean_power_w: float
    energy: EnergyMetrics
    #: Validated on energy rather than per-sample error, as a fixed power cannot follow a cycling load.
    has_fixed_power: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "activity": self.activity.value if self.activity is not None else UNEXPLAINED_ACTIVITY,
            "sample_count": self.sample_count,
            "episode_count": self.episode_count,
            "validation_count": self.validation_count,
            "coverage": round(self.coverage, 4),
            "mae_w": round(self.mae_w, 3) if self.mae_w is not None else None,
            "transition_mae_w": round(self.transition_mae_w, 3) if self.transition_mae_w is not None else None,
            "mean_power_w": self.mean_power_w,
            **self.energy.to_dict(),
        }


@dataclass(frozen=True)
class EvaluatedCandidate:
    candidate: AnalysisCandidate
    metrics: AnalysisMetrics
    activity_reports: list[ActivityReport] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisFailure:
    reason: str
    activity_reports: list[ActivityReport] = field(default_factory=list)


@dataclass(frozen=True)
class RecorderAnalysisResult:
    status: AnalysisStatus
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
        return self.status == AnalysisStatus.MODEL_READY and self.model_config_fragment is not None

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": 1,
            "status": self.status.value,
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
        value.update(self._build_validation_details())
        return value

    def _build_validation_details(self) -> dict[str, object]:
        details: dict[str, object] = {}
        if self.features:
            details["features"] = [feature.identifier for feature in self.features]
        if self.validation_method is not None:
            details["validation_method"] = self.validation_method.value
        if self.activity_reports:
            details["activities"] = [report.to_dict() for report in self.activity_reports]
        return details

    def build_summary(self) -> dict[str, str]:
        if not self.model_ready:
            summary = {RECORDING_ANALYSIS_LABEL: "More data needed"}
            if self.reason is not None:
                summary["Recording analysis reason"] = self.reason
            return summary
        assert self.feature is not None
        assert self.metrics is not None
        assert self.model_config_fragment is not None
        if self.strategy == "vacuum_composite":
            return {
                RECORDING_ANALYSIS_LABEL: "Composite vacuum profile created",
                "Analysed inputs": ", ".join(feature.identifier for feature in self.features),
                "Validation MAE": f"{self.metrics.mae_w:.2f} W",
                "Validation coverage": f"{self.metrics.coverage:.0%}",
                "Validation method": self.validation_method.value if self.validation_method else "held-out episodes",
                "Recorded activities": ", ".join(
                    report.activity for report in self.activity_reports if report.activity is not None
                ),
            }
        fixed_config = self.model_config_fragment.configuration
        profile_type = "Fixed power" if "power" in fixed_config else "Fixed states_power"
        if self.model_config_fragment.calculation_strategy == "composite":
            profile_type = "State-based composite"
        return {
            RECORDING_ANALYSIS_LABEL: f"{profile_type} profile created",
            "Analysed feature": self.feature.identifier,
            "Validation MAE": f"{self.metrics.mae_w:.2f} W",
            "Validation coverage": f"{self.metrics.coverage:.0%}",
            "Validation method": self.validation_method.value if self.validation_method else "unknown",
        }
