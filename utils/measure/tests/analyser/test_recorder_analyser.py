from dataclasses import dataclass
import json
from pathlib import Path

from measure.analyser.fixed import FixedStatesPowerStrategy
from measure.analyser.models import (
    AnalysisContext,
    AnalysisMetrics,
    FeatureReference,
    ModelConfigFragment,
    RecordedEntity,
    RecordedEntityState,
    RecorderAnalysisResult,
    RecordingSample,
    StrategyNotApplicable,
)
from measure.analyser.recording import load_recording
from measure.analyser.service import RecorderAnalyser, _credibility_reason, _select_candidate, analysis_context_for
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import RecorderMeasurementRequest, RecorderProfileRecipe, RecorderPurpose
import pytest

CONTEXT = AnalysisContext(
    recipe="generic",
    primary_entity_id="switch.device",
    device_type="generic_iot",
    entities=(RecordedEntity("switch.device", "switch", "primary"),),
)


@dataclass(frozen=True)
class RecorderRegressionCase:
    fixture: str
    context: AnalysisContext
    strategy: str
    feature: FeatureReference
    model_config_fragment: dict[str, object]
    standby_power: float | None
    sample_count: int
    validation_mae_w: float
    validation_coverage: float


RECORDER_REGRESSION_CASES = (
    RecorderRegressionCase(
        fixture="set_top_box_two_states.jsonl",
        context=AnalysisContext(
            recipe="generic",
            primary_entity_id="media_player.kpn_diw7022",
            device_type="generic_iot",
            entities=(RecordedEntity("media_player.kpn_diw7022", "media_player", "primary"),),
        ),
        strategy="fixed_states_power",
        feature=FeatureReference("media_player.kpn_diw7022", "state"),
        model_config_fragment={
            "calculation_strategy": "fixed",
            "fixed_config": {"power": 3.1},
        },
        standby_power=2.4,
        sample_count=228,
        validation_mae_w=0.162,
        validation_coverage=1,
    ),
)


def sample(
    index: int,
    power: float,
    state: str,
    attributes: dict[str, object] | None = None,
) -> RecordingSample:
    return RecordingSample(
        elapsed_seconds=float(index),
        power=power,
        entities={"switch.device": RecordedEntityState(state, attributes or {})},
    )


def write_recording(path: Path, samples: list[RecordingSample], *, typed: bool = True) -> None:
    records: list[dict[str, object]] = []
    if typed:
        records.append(CONTEXT.metadata_record())
    records.extend(
        {
            **({"record_type": "sample"} if typed else {}),
            "elapsed_seconds": item.elapsed_seconds,
            "power": item.power,
            "entities": {
                entity_id: {"state": state.state, "attributes": state.attributes}
                for entity_id, state in item.entities.items()
            },
        }
        for item in samples
    )
    path.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")


@pytest.mark.parametrize(
    "case",
    RECORDER_REGRESSION_CASES,
    ids=lambda case: case.fixture.removesuffix(".jsonl"),
)
def test_real_world_recorder_regressions(case: RecorderRegressionCase) -> None:
    path = Path(__file__).parent / "fixtures" / case.fixture

    result = RecorderAnalyser().analyse(path, case.context)

    assert result.model_ready
    assert result.sample_count == case.sample_count
    assert result.strategy == case.strategy
    assert result.feature == case.feature
    assert result.model_config_fragment is not None
    assert result.model_config_fragment.to_dict() == case.model_config_fragment
    assert result.standby_power == pytest.approx(case.standby_power)
    assert result.metrics is not None
    assert result.metrics.mae_w == pytest.approx(case.validation_mae_w, abs=0.001)
    assert result.metrics.coverage == pytest.approx(case.validation_coverage)


def test_load_recording_accepts_typed_and_legacy_samples_and_reports_bad_lines(tmp_path: Path) -> None:
    path = tmp_path / "record.jsonl"
    write_recording(path, [sample(0, 1.2, "idle")])
    with path.open("a", encoding="utf-8") as recording:
        recording.write('{"broken":true}\n')
        recording.write("not json\n")

    loaded = load_recording(path)

    assert loaded.dataset.metadata is not None
    assert loaded.dataset.samples == (sample(0, 1.2, "idle"),)
    assert len(loaded.warnings) == 1
    assert "Skipped 2 invalid recorder line(s)" in loaded.warnings[0]
    assert "line 3" in loaded.warnings[0]

    legacy = tmp_path / "legacy.jsonl"
    write_recording(legacy, [sample(1, 2.3, "active")], typed=False)
    assert load_recording(legacy).dataset.samples == (sample(1, 2.3, "active"),)


@pytest.mark.parametrize(
    "record",
    [
        [],
        {"record_type": "future"},
        {"elapsed_seconds": float("inf"), "power": 1, "entities": {}},
        {"elapsed_seconds": True, "power": 1, "entities": {}},
        {"elapsed_seconds": [], "power": 1, "entities": {}},
        {"elapsed_seconds": 1, "power": 1, "entities": []},
        {"elapsed_seconds": 1, "power": 1, "entities": {"switch.device": []}},
        {"elapsed_seconds": 1, "power": 1, "entities": {"switch.device": {"state": 1}}},
    ],
)
def test_load_recording_skips_unsupported_and_invalid_records(tmp_path: Path, record: object) -> None:
    path = tmp_path / "record.jsonl"
    path.write_text(f"{json.dumps(record)}\n", encoding="utf-8")

    loaded = load_recording(path)

    assert loaded.dataset.samples == ()
    assert len(loaded.warnings) == (0 if record == {"record_type": "future"} else 1)


def test_fixed_strategy_builds_a_lookup_candidate_for_primary_state() -> None:
    samples = [sample(index, 0.2 if index % 2 == 0 else 5.2, "off" if index % 2 == 0 else "on") for index in range(8)]

    candidate = FixedStatesPowerStrategy().build_candidate(samples, CONTEXT)

    assert not isinstance(candidate, StrategyNotApplicable)
    assert candidate.feature == FeatureReference("switch.device", "state")
    assert candidate.estimate_power(sample(20, 99, "on")) == pytest.approx(5.2)
    assert candidate.estimate_power(sample(21, 99, "unknown")) is None
    assert candidate.standby_power == pytest.approx(0.2)
    assert candidate.build_model_config_fragment().to_dict() == {
        "calculation_strategy": "fixed",
        "fixed_config": {"power": 5.2},
    }

    missing_entity = RecordingSample(30, 1, {})
    assert candidate.estimate_power(missing_entity) is None


def test_fixed_strategy_ignores_unavailable_values_and_non_scalar_attributes() -> None:
    samples = [sample(index, 2.0 if index % 2 else 8.0, "unavailable", {"mode": ["invalid"]}) for index in range(8)]

    result = FixedStatesPowerStrategy().build_candidate(samples, CONTEXT)

    assert isinstance(result, StrategyNotApplicable)


def test_fixed_strategy_keeps_multiple_active_states_as_states_power() -> None:
    samples = [
        sample(index, (2.0, 5.0, 8.0)[index % 3], ("idle", "playing", "recording")[index % 3]) for index in range(12)
    ]

    candidate = FixedStatesPowerStrategy().build_candidate(samples, CONTEXT)

    assert not isinstance(candidate, StrategyNotApplicable)
    assert candidate.build_model_config_fragment().to_dict() == {
        "calculation_strategy": "fixed",
        "fixed_config": {"states_power": {"idle": 2.0, "playing": 5.0, "recording": 8.0}},
    }


def test_feature_reference_accepts_finite_scalar_attributes_only() -> None:
    feature = FeatureReference("switch.device", "attribute", "value")

    assert feature.value(sample(1, 1, "on", {"value": 2.5})) == pytest.approx(2.5)
    assert feature.value(sample(1, 1, "on", {"value": float("nan")})) is None
    assert feature.value(sample(1, 1, "on", {"value": float("inf")})) is None


def test_recorded_entity_and_analysis_result_include_optional_evidence() -> None:
    entity = RecordedEntity(
        "switch.device",
        "switch",
        "primary",
        device_class="outlet",
        integration="test",
        translation_key="plug",
    )
    result = RecorderAnalysisResult(
        status="insufficient_data",
        sample_count=3,
        reason="more data",
        warnings=("bad line",),
    )

    assert entity.to_dict()["translation_key"] == "plug"
    assert result.to_dict()["warnings"] == ["bad line"]


def test_analyser_selects_scalar_attribute_when_state_is_constant(tmp_path: Path) -> None:
    path = tmp_path / "record.jsonl"
    samples = [
        sample(index, 2.0 if index % 2 == 0 else 8.0, "on", {"mode": "eco" if index % 2 == 0 else "boost"})
        for index in range(20)
    ]
    write_recording(path, samples)

    result = RecorderAnalyser().analyse(path, CONTEXT)

    assert result.model_ready
    assert result.feature == FeatureReference("switch.device", "attribute", "mode")
    assert result.metrics is not None
    assert result.metrics.coverage == pytest.approx(1)
    assert result.metrics.mae_w == pytest.approx(0)
    assert result.standby_power is None
    assert result.model_config_fragment is not None
    assert result.model_config_fragment.to_dict()["fixed_config"] == {
        "states_power": {"mode|boost": 8.0, "mode|eco": 2.0},
    }


def test_analyser_accepts_a_meaningful_relative_improvement_for_a_low_power_device(tmp_path: Path) -> None:
    path = tmp_path / "record.jsonl"
    samples = [sample(index, 2.4 if index < 5 else 3.1, "off" if index < 5 else "on") for index in range(50)]
    write_recording(path, samples)

    result = RecorderAnalyser().analyse(path, CONTEXT)

    assert result.model_ready
    assert result.model_config_fragment is not None
    assert result.model_config_fragment.to_dict()["fixed_config"] == {
        "power": 3.1,
    }


@pytest.mark.parametrize(
    "samples,reason",
    [
        ([sample(index, 3.0, "on") for index in range(10)], "No state or scalar attribute"),
        ([sample(index, float(index), f"state_{index}") for index in range(25)], "No state or scalar attribute"),
        (
            [sample(index, 1.0 if index % 2 else 1.05, "on" if index % 2 else "off") for index in range(20)],
            "not reliable enough",
        ),
    ],
)
def test_analyser_rejects_recordings_without_a_credible_fixed_model(
    tmp_path: Path,
    samples: list[RecordingSample],
    reason: str,
) -> None:
    path = tmp_path / "record.jsonl"
    write_recording(path, samples)

    result = RecorderAnalyser().analyse(path, CONTEXT)

    assert not result.model_ready
    assert result.status == "insufficient_data"
    assert reason in str(result.reason)
    assert result.summary() == {
        "Recording analysis": "More data needed",
        "Recording analysis reason": result.reason,
    }


def test_analyser_explains_which_credibility_threshold_was_not_met(tmp_path: Path) -> None:
    path = tmp_path / "record.jsonl"
    write_recording(
        path,
        [sample(index, 1.0 if index % 2 else 1.05, "on" if index % 2 else "off") for index in range(20)],
    )

    result = RecorderAnalyser().analyse(path, CONTEXT)

    assert result.reason == (
        "The state-based profile was not reliable enough: its power estimates differed by only 0.05 W between "
        "recorded values; at least 0.10 W is required."
    )


def test_credibility_reason_reports_coverage_and_improvement_values() -> None:
    reason = _credibility_reason(
        "composite",
        AnalysisMetrics(20, 4, 0.5, 0.95, 1.0, 5),
        AnalysisMetrics(20, 4, 1.0, 1.0, 1.0, 5),
        prediction_range=2,
    )

    assert reason == (
        "The composite profile was not reliable enough: it could estimate 50% of validation samples; at least 90% "
        "is required; it reduced the typical validation difference from 1.00 W to 0.95 W (5%); at least 0.10 W "
        "or 15% improvement is required."
    )


def test_analyser_requires_enough_samples(tmp_path: Path) -> None:
    path = tmp_path / "record.jsonl"
    write_recording(path, [sample(index, float(index % 2), "on" if index % 2 else "off") for index in range(9)])

    result = RecorderAnalyser().analyse(path, CONTEXT)

    assert result.reason == "Record at least 10 valid samples across device states"
    assert result.to_dict()["sample_count"] == 9


def test_analyser_reports_when_no_registered_strategy_can_explain_recording(tmp_path: Path) -> None:
    path = tmp_path / "record.jsonl"
    write_recording(
        path,
        [sample(index, 2 if index % 2 else 8, "idle" if index % 2 else "active") for index in range(10)],
    )

    result = RecorderAnalyser(strategies=()).analyse(path, CONTEXT)

    assert result.reason == "No analysis strategy could explain the recorded power"


def test_analyser_requires_five_recorded_samples_for_every_model_value(tmp_path: Path) -> None:
    path = tmp_path / "record.jsonl"
    samples = [
        *[sample(index, 2, "idle") for index in range(4)],
        *[sample(index, 8, "active") for index in range(4, 10)],
    ]
    write_recording(path, samples)

    result = RecorderAnalyser().analyse(path, CONTEXT)

    assert not result.model_ready
    assert "at least 5 samples for every value" in str(result.reason)


def test_analysis_context_maps_generic_and_vacuum_recipes() -> None:
    generic = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose=RecorderPurpose.COMPLEX_PROFILE,
        profile_recipe=RecorderProfileRecipe.GENERIC,
        tracked_entity_ids=("switch.device", "sensor.mode"),
    )
    vacuum = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose=RecorderPurpose.COMPLEX_PROFILE,
        profile_recipe=RecorderProfileRecipe.VACUUM_ROBOT,
        vacuum_entity_id="vacuum.robot",
        battery_entity_id="sensor.robot_battery",
    )

    assert analysis_context_for(generic).device_type == "generic_iot"
    assert generic.generate_model_json is False
    vacuum_context = analysis_context_for(vacuum)
    assert vacuum_context.device_type == "vacuum_robot"
    assert [entity.role for entity in vacuum_context.entities] == ["primary", "battery"]

    playbook = RecorderMeasurementRequest(power_meter=DummyPowerMeterSpec())
    with pytest.raises(ValueError, match="complex-profile"):
        analysis_context_for(playbook)


class _Candidate:
    strategy_id = "test"
    feature = FeatureReference("switch.device", "state")
    standby_power = None

    def __init__(self, complexity: int) -> None:
        self.complexity = complexity

    def estimate_power(self, sample: RecordingSample) -> float | None:
        return sample.power

    def build_model_config_fragment(self) -> ModelConfigFragment:
        return ModelConfigFragment("fixed", "fixed_config", {})


def test_selector_only_prefers_complex_candidate_for_material_error_improvement() -> None:
    simple = _Candidate(2)
    complex_candidate = _Candidate(3)
    base = AnalysisMetrics(20, 4, 1, 1.0, 1.0, 5)

    selected, _ = _select_candidate([(complex_candidate, AnalysisMetrics(20, 4, 1, 0.95, 1, 5)), (simple, base)])
    assert selected is simple

    selected, _ = _select_candidate([(simple, base), (complex_candidate, AnalysisMetrics(20, 4, 1, 0.8, 1, 5))])
    assert selected is complex_candidate

    equal_complexity = _Candidate(2)
    selected, _ = _select_candidate([(simple, base), (equal_complexity, AnalysisMetrics(20, 4, 1, 0.9, 1, 5))])
    assert selected is equal_complexity
