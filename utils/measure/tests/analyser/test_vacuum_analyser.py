from dataclasses import replace
import json
from pathlib import Path

from measure.analyser.execution import RecorderAnalysisExecution
from measure.analyser.fixed import FixedStatesPowerCandidate
from measure.analyser.models import (
    ActivityReport,
    AnalysisContext,
    EnergyMetrics,
    FeatureReference,
    ModelConfigFragment,
    RecordedEntity,
    RecordedEntityState,
    RecorderAnalysisResult,
    RecordingSample,
    StrategyNotApplicable,
    TrainingValidationSplit,
    ValidationMethod,
)
from measure.analyser.recording import load_recordings, recording_context
from measure.analyser.service import RecorderAnalyser
from measure.analyser.vacuum import (
    ChargingPoint,
    VacuumBranch,
    VacuumCompositeCandidate,
    VacuumCompositeStrategy,
    battery_level,
    split_vacuum_samples,
    vacuum_episodes,
)
from measure.analyser.vacuum_signals import (
    Activity,
    ActivitySignal,
    discover_signals,
    portable_entity,
    resolve_activity,
)
from measure.analyser.vacuum_validation import activity_reports, credibility_failure
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import RecorderMeasurementRequest
import pytest

PRIMARY = "vacuum.robot"
BATTERY = "sensor.battery"
STATE = "sensor.activity"
DRYING = "binary_sensor.drying"
CONTEXT = AnalysisContext(
    "vacuum_robot",
    PRIMARY,
    "vacuum_robot",
    [
        RecordedEntity(PRIMARY, "vacuum", "primary", device_id="robot"),
        RecordedEntity(BATTERY, "sensor", "battery", device_class="battery", unit="%", device_id="robot"),
        RecordedEntity(STATE, "sensor", "tracked", translation_key="state", device_id="robot"),
        RecordedEntity(DRYING, "binary_sensor", "tracked", translation_key="drying", device_id="robot"),
        RecordedEntity("switch.auto_drying", "switch", "tracked", translation_key="auto_drying", device_id="robot"),
    ],
)


def test_session_analysis_uses_archived_vacuum_run_for_fitting(tmp_path: Path) -> None:
    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id=PRIMARY,
        battery_entity_id=BATTERY,
        additional_entity_ids=(STATE, DRYING, "switch.auto_drying"),
    )
    write_recording(tmp_path / "record.jsonl", cycle())
    execution = RecorderAnalysisExecution()
    assert execution.run(request, tmp_path)["Recording analysis"] == "More data needed"
    write_recording(tmp_path / "record-1.jsonl", cycle())

    summary = execution.run(request, tmp_path)

    assert summary["Recording analysis"] == "Composite vacuum profile created"
    assert summary["Recordings analysed"] == "2"
    assert summary["Samples analysed"] == str(2 * len(cycle()))
    result = json.loads((tmp_path / "analyser.json").read_text())
    assert result["validation_method"] == "held_out_recording"
    assert json.loads((tmp_path / "model.json").read_text())["calculation_strategy"] == "composite"


def sample(activity: str, power: float, index: int = 0, level: object = 50) -> RecordingSample:
    return RecordingSample(
        float(index),
        power,
        {
            PRIMARY: RecordedEntityState(
                "docked" if activity not in {"cleaning", "returning"} else activity,
                {
                    "vacuum_state": activity,
                    "washing": activity == "washing",
                    "drying": activity == "drying",
                    "auto_empty_status": activity == "auto_emptying",
                    "battery_level": level,
                },
            ),
            BATTERY: RecordedEntityState(str(level), {}),
            STATE: RecordedEntityState(activity, {}),
            DRYING: RecordedEntityState("on" if activity == "drying" else "off", {}),
            "switch.auto_drying": RecordedEntityState("on", {}),
        },
    )


def cycle() -> list[RecordingSample]:
    result = []
    for activity, power in (("sleeping", 3.5), ("washing", 22), ("auto_emptying", 600), ("drying", 7)):
        result.extend(sample(activity, power, len(result) + index) for index in range(10))
    for level in range(20, 81, 10):
        result.extend(sample("charging", 50 - level / 2, len(result) + index, level) for index in range(3))
    result.extend(sample("cleaning", 0.3, len(result) + index) for index in range(10))
    return [replace(item, elapsed_seconds=float(index)) for index, item in enumerate(result)]


def repeated() -> list[RecordingSample]:
    first = cycle()
    return first + [replace(item, elapsed_seconds=item.elapsed_seconds + len(first)) for item in cycle()]


def write_recording(path: Path, samples: list[RecordingSample], context: AnalysisContext | None = CONTEXT) -> Path:
    records = [context.metadata_record()] if context is not None else []
    records.extend(
        {
            "elapsed_seconds": item.elapsed_seconds,
            "power": item.power,
            "entities": {
                key: {"state": value.state, "attributes": dict(value.attributes)}
                for key, value in item.entities.items()
            },
        }
        for item in samples
    )
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def candidate(
    samples: list[RecordingSample] | None = None, context: AnalysisContext = CONTEXT
) -> VacuumCompositeCandidate:
    result = VacuumCompositeStrategy().build_candidate(samples if samples is not None else cycle(), context)
    assert isinstance(result, VacuumCompositeCandidate)
    return result


def test_composite_features_preserve_order_without_duplicates() -> None:
    model = candidate()
    expected = [
        FeatureReference(PRIMARY, "attribute", "auto_empty_status"),
        FeatureReference(PRIMARY, "attribute", "washing"),
        FeatureReference(DRYING, "state"),
        FeatureReference(STATE, "state"),
        FeatureReference(BATTERY, "state"),
    ]

    assert model.features == expected
    model.features.clear()
    assert model.features == expected


def test_composite_profile_from_separate_entities(tmp_path: Path) -> None:
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", repeated()), CONTEXT)
    assert result.model_ready
    assert result.strategy == "vacuum_composite"
    assert result.validation_method is ValidationMethod.HELD_OUT_EPISODES
    assert json.loads(json.dumps(result.to_dict()))["validation_method"] == "held_out_episodes"
    assert result.summary()["Validation method"] == "held_out_episodes"
    assert result.metrics is not None
    assert result.metrics.mae_w == 0
    assert result.metrics.coverage == 1
    assert result.standby_power == 3.5
    assert {report.activity for report in result.activity_reports} == {
        "sleeping",
        "washing",
        "auto_emptying",
        "drying",
        "charging",
        "away",
    }
    assert all(report.episode_count == 2 for report in result.activity_reports)
    assert all(report.energy.bias_percent == 0 for report in result.activity_reports)
    assert STATE + ".state" in result.to_dict()["features"]
    assert result.summary()["Recording analysis"] == "Composite vacuum profile created"
    fragment = result.model_config_fragment
    assert fragment is not None
    config = fragment.to_dict()["composite_config"]
    assert config["mode"] == "stop_at_first"
    branches = config["strategies"]
    assert len(branches) == 6
    charging = next(branch for branch in branches if "linear" in branch)
    assert charging["entity_id"] == "[[entity_by_device_class:battery]]"
    assert len(charging["linear"]["calibrate"]) == 7
    assert "[[entity_by_translation_key:state]]" in json.dumps(charging["condition"])
    assert "auto_drying" not in json.dumps(fragment.to_dict())
    assert not any("state" not in json.dumps(branch["condition"]) for branch in branches)


def test_whole_recording_validation_and_captured_metadata(tmp_path: Path) -> None:
    paths = [write_recording(tmp_path / f"record-{index}.jsonl", cycle()) for index in range(2)]
    bare = replace(CONTEXT, entities=[RecordedEntity(e.entity_id, e.domain, e.role) for e in CONTEXT.entities])
    result = RecorderAnalyser().analyse(paths, bare)
    assert result.model_ready
    assert result.validation_method is ValidationMethod.HELD_OUT_RECORDING
    assert json.loads(json.dumps(result.to_dict()))["validation_method"] == "held_out_recording"
    assert result.summary()["Validation method"] == "held_out_recording"
    assert result.metrics is not None
    assert result.metrics.validation_count == len(cycle())
    assert candidate().complexity == 12
    assert candidate().feature == candidate().features[0]


def test_single_cycle_is_not_independent_evidence(tmp_path: Path) -> None:
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", cycle()), CONTEXT)
    assert not result.model_ready
    assert "two independent episodes" in str(result.reason)


def test_short_mode_error_is_not_hidden_by_long_idle(tmp_path: Path) -> None:
    data = repeated()
    second_start = len(cycle())
    data = [
        replace(item, power=100) if index >= second_start and item.entities[STATE].state == "washing" else item
        for index, item in enumerate(data)
    ]
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", data), CONTEXT)
    assert not result.model_ready
    assert "washing validation error" in str(result.reason)
    assert result.activity_reports
    assert result.validation_method is ValidationMethod.HELD_OUT_EPISODES


@pytest.mark.parametrize("state", ["unknown", "unavailable", "new_mode"])
def test_unknown_runtime_state_is_not_a_zero_or_docked_fallback(state: str) -> None:
    item = sample("sleeping", 3.5)
    item = replace(item, entities={**item.entities, STATE: RecordedEntityState(state, {})})
    assert candidate().estimate_power(item) is None


def test_precedence_active_drying_not_enabled_setting() -> None:
    data = cycle()
    changed = []
    for item in data:
        if item.entities[STATE].state == "drying":
            primary = item.entities[PRIMARY]
            item = replace(
                item,
                entities={
                    **item.entities,
                    PRIMARY: replace(primary, attributes={**primary.attributes, "vacuum_state": "charging_completed"}),
                    STATE: RecordedEntityState("charging_completed", {}),
                },
            )
        changed.append(item)
    model = candidate(changed)
    assert model.estimate_power(changed[35]) == 7
    assert model.estimate_power(changed[0]) == 3.5
    assert model.features.count(FeatureReference(DRYING, "state")) == 1


def test_unmeasured_activity_guard_and_missing_flag() -> None:
    model = candidate()
    item = sample("sleeping", 3.5)
    primary = item.entities[PRIMARY]
    assert (
        model.estimate_power(
            replace(
                item,
                entities={
                    **item.entities,
                    PRIMARY: replace(primary, attributes={**primary.attributes, "washing": True}),
                },
            )
        )
        == 22
    )
    assert (
        model.estimate_power(
            replace(item, entities={key: value for key, value in item.entities.items() if key != DRYING})
        )
        is None
    )
    assert (
        ActivitySignal(Activity.WASHING, FeatureReference(PRIMARY, "attribute", "washing"), [True], [False]).matches(
            replace(item, entities={**item.entities, PRIMARY: replace(primary, attributes={"washing": 1})})
        )
        is None
    )


@pytest.mark.parametrize("level", ["unknown", "unavailable", "bad", True, -1, 101, "NaN", "inf"])
def test_invalid_battery_levels(level: object) -> None:
    item = sample("charging", 10, level=level)
    feature = FeatureReference(PRIMARY, "attribute", "battery_level")
    assert battery_level(item, feature) is None
    assert candidate().estimate_power(item) is None


def test_charging_range_integer_conversion_and_attribute_fallback() -> None:
    model = candidate()
    assert model.estimate_power(sample("charging", 0, level="45.9")) == 27.5
    assert model.estimate_power(sample("charging", 0, level=19)) is None
    assert model.estimate_power(sample("charging", 0, level=81)) is None
    bare = replace(CONTEXT, entities=[RecordedEntity(e.entity_id, e.domain, e.role) for e in CONTEXT.entities])
    model = candidate(context=bare)
    assert model.battery == FeatureReference(PRIMARY, "attribute", "battery_level")
    fragment = model.build_model_config_fragment().to_dict()
    charging = next(branch for branch in fragment["composite_config"]["strategies"] if "linear" in branch)
    assert charging["entity_id"] == "[[entity]]"
    assert charging["linear"]["attribute"] == "battery_level"
    assert battery_level(sample("charging", 1), None) is None


@pytest.mark.parametrize(
    "levels,reason", [([20, 25, 30], "20 battery"), ([20, 50, 80], "coverage gap"), ([20, 80], "three battery")]
)
def test_unsupported_charging_curves(levels: list[int], reason: str) -> None:
    data = [sample("sleeping", 3.5, index) for index in range(5)]
    data += [sample("charging", 20, len(data) + index, level) for level in levels for index in range(3)]
    result = VacuumCompositeStrategy().build_candidate(data, CONTEXT)
    assert isinstance(result, StrategyNotApplicable)
    assert reason in result.reason


def test_charging_requires_portable_battery_not_entity_name() -> None:
    data = [
        replace(
            item,
            entities={
                **item.entities,
                PRIMARY: replace(
                    item.entities[PRIMARY],
                    attributes={
                        key: value for key, value in item.entities[PRIMARY].attributes.items() if key != "battery_level"
                    },
                ),
            },
        )
        for item in cycle()
    ]
    bare = replace(CONTEXT, entities=[RecordedEntity(e.entity_id, e.domain, e.role) for e in CONTEXT.entities])
    result = VacuumCompositeStrategy().build_candidate(data, bare)
    assert isinstance(result, StrategyNotApplicable)
    assert "portable battery metadata" in result.reason


def test_portable_references_require_unique_same_device_metadata() -> None:
    assert portable_entity(PRIMARY, CONTEXT) == "[[entity]]"
    assert portable_entity(STATE, CONTEXT) == "[[entity_by_translation_key:state]]"
    assert portable_entity("sensor.missing", CONTEXT) is None
    duplicate = RecordedEntity(
        "sensor.duplicate", "sensor", "disabled", translation_key="state", device_id="robot", disabled_by="user"
    )
    assert portable_entity(STATE, replace(CONTEXT, device_entities=[*CONTEXT.entities, duplicate])) is None
    other = replace(CONTEXT.entities[2], device_id="other")
    assert portable_entity(STATE, replace(CONTEXT, entities=[*CONTEXT.entities[:2], other])) is None
    duplicate_battery = replace(duplicate, translation_key=None, device_class="battery")
    assert portable_entity(BATTERY, replace(CONTEXT, device_entities=[*CONTEXT.entities, duplicate_battery])) is None


def test_telemetry_gaps_are_not_independent_cycles() -> None:
    first = sample("sleeping", 3.5)
    data = [
        first,
        replace(first, elapsed_seconds=31),
        replace(first, elapsed_seconds=32),
        replace(first, recording_id=1, elapsed_seconds=0),
        replace(first, recording_id=1, elapsed_seconds=0),
    ]
    episodes = vacuum_episodes(data, discover_signals(data, CONTEXT))
    assert [len(episode.samples) for episode in episodes] == [3, 2]
    assert vacuum_episodes([], []) == []


def test_unexplained_episodes_are_held_out_and_reported(tmp_path: Path) -> None:
    data = repeated() + [sample("unrecognised_mode", 20, len(repeated()) + index) for index in range(20)]
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", data), CONTEXT)
    assert not result.model_ready
    assert "20 of 162 samples match no known activity" in str(result.reason)
    assert result.to_dict()["activities"][-1]["activity"] == "unexplained"
    assert result.activity_reports[-1].mae_w is None


def test_brief_unexplained_blip_does_not_reject_recording(tmp_path: Path) -> None:
    data = repeated()
    data[15] = replace(sample("unrecognised_mode", 22), elapsed_seconds=data[15].elapsed_seconds)
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", data), CONTEXT)
    assert result.model_ready
    assert "unexplained" in {report.activity for report in result.activity_reports}


def test_energy_only_integrates_adjacent_held_out_samples() -> None:
    data = repeated()
    model = candidate()
    reports = activity_reports(model, data, [data[0], data[2], replace(data[3], recording_id=99)])
    assert all(report.energy.duration_seconds == 0 for report in reports)
    assert all(report.energy.bias_percent is None for report in reports)
    assert credibility_failure(reports) is not None


def test_strategy_rejections_and_empty_recordings(tmp_path: Path) -> None:
    strategy = VacuumCompositeStrategy()
    assert isinstance(strategy.build_candidate(cycle(), replace(CONTEXT, recipe="generic")), StrategyNotApplicable)
    assert isinstance(strategy.build_candidate([sample("sleeping", 3.5)] * 10, CONTEXT), StrategyNotApplicable)
    result = strategy.build_candidate([replace(item, power=-1) for item in cycle()], CONTEXT)
    assert isinstance(result, StrategyNotApplicable)
    assert "non-negative" in result.reason
    assert isinstance(
        strategy.build_candidate([sample("sleeping", 3)] * 5 + [sample("washing", 22)], CONTEXT), StrategyNotApplicable
    )
    assert isinstance(split_vacuum_samples([sample("mystery", 1)] * 20, CONTEXT), StrategyNotApplicable)
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", []), CONTEXT)
    assert not result.model_ready


def test_metadata_validation_and_legacy_loading(tmp_path: Path) -> None:
    path = write_recording(tmp_path / "first.jsonl", cycle())
    different = write_recording(tmp_path / "second.jsonl", cycle(), replace(CONTEXT, recipe="generic"))
    with pytest.raises(ValueError, match="same recipe"):
        load_recordings([path, different])
    with pytest.raises(ValueError, match="at least one"):
        load_recordings([])
    legacy = write_recording(tmp_path / "legacy.jsonl", cycle(), None)
    assert load_recordings([legacy]).dataset.metadata is None
    assert recording_context(CONTEXT, None) == CONTEXT
    assert recording_context(CONTEXT, {"recipe": "generic"}) == CONTEXT
    enriched = recording_context(
        CONTEXT,
        {
            "recipe": "vacuum_robot",
            "primary_entity_id": PRIMARY,
            "entities": [
                None,
                {"entity_id": 3},
                {
                    "entity_id": PRIMARY,
                    "domain": "vacuum",
                    "role": "tracked",
                    "device_id": "new",
                    "has_live_state": True,
                    "unit": 8,
                },
            ],
            "device_entities": {},
        },
    )
    assert enriched.entities[0].role == "primary"
    assert enriched.entities[0].device_id == "new"
    assert enriched.entities[0].unit is None
    assert enriched.entities[0].has_live_state is True


def test_fragment_sequence_and_report_serialization() -> None:
    fixed = FixedStatesPowerCandidate(FeatureReference(PRIMARY, "state"), {"docked": 3, "cleaning": 0.3})
    assert fixed.features == [fixed.feature]
    assert ModelConfigFragment("composite", "composite_config", [{"fixed": {"power": 2}}]).to_dict()[
        "composite_config"
    ] == [{"fixed": {"power": 2}}]
    result = RecorderAnalysisResult(
        "insufficient_data",
        10,
        validation_method=ValidationMethod.HELD_OUT_RECORDING,
        activity_reports=activity_reports(candidate(), repeated(), cycle()),
    )
    assert result.to_dict()["validation_method"] == "held_out_recording"
    assert "activities" in result.to_dict()
    assert resolve_activity(sample("sleeping", 3.5), ()) is None
    assert VacuumBranch(Activity.AWAY, 0.3).estimate(sample("cleaning", 0.3), None) == 0.3


def test_activity_report_preserves_flat_json_contract() -> None:
    report = ActivityReport(
        activity="washing",
        sample_count=20,
        episode_count=2,
        validation_count=10,
        coverage=1,
        mae_w=0.2,
        transition_mae_w=0.4,
        mean_power_w=22,
        energy=EnergyMetrics(duration_seconds=9, measured_wh=0.055, predicted_wh=0.056, bias_percent=1.82),
    )
    result = RecorderAnalysisResult("insufficient_data", 20, activity_reports=[report])
    assert result.to_dict()["activities"] == [
        {
            "activity": "washing",
            "sample_count": 20,
            "episode_count": 2,
            "validation_count": 10,
            "coverage": 1,
            "mae_w": 0.2,
            "transition_mae_w": 0.4,
            "mean_power_w": 22,
            "energy_duration_seconds": 9,
            "measured_energy_wh": 0.055,
            "predicted_energy_wh": 0.056,
            "energy_bias_percent": 1.82,
        }
    ]


@pytest.mark.parametrize("separate_recordings", [False, True])
def test_analysis_split_keeps_training_and_validation_separate(separate_recordings: bool) -> None:
    training = cycle()
    validation = [
        replace(item, elapsed_seconds=item.elapsed_seconds + len(training), recording_id=int(separate_recordings))
        for item in cycle()
    ]
    split = split_vacuum_samples(training + validation, CONTEXT)
    assert isinstance(split, TrainingValidationSplit)
    assert split.training == training
    assert split.validation == validation
    assert split.method is (
        ValidationMethod.HELD_OUT_RECORDING if separate_recordings else ValidationMethod.HELD_OUT_EPISODES
    )
    assert {id(item) for item in split.training}.isdisjoint(id(item) for item in split.validation)


def test_charging_points_interpolate_between_named_coordinates() -> None:
    branch = VacuumBranch(
        Activity.CHARGING,
        calibration=[
            ChargingPoint(battery_level=20, power=40),
            ChargingPoint(battery_level=40, power=30),
            ChargingPoint(battery_level=80, power=10),
        ],
    )
    battery = FeatureReference(BATTERY, "state")
    assert branch.estimate(sample("charging", 0, level=20), battery) == 40
    assert branch.estimate(sample("charging", 0, level=50), battery) == 25
    assert branch.estimate(sample("charging", 0, level=80), battery) == 10
    assert branch.estimate(sample("charging", 0, level=81), battery) is None


def test_standby_requires_a_measured_standby_activity() -> None:
    assert candidate([sample("cleaning", 0.3)] * 10 + [sample("washing", 22)] * 10).standby_power is None


def test_negative_held_out_measurements_are_rejected(tmp_path: Path) -> None:
    data = repeated()
    data[-1] = replace(data[-1], power=-0.1)
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", data), CONTEXT)
    assert not result.model_ready
    assert "non-negative" in str(result.reason)


def test_unmeasured_flag_blocks_fallback() -> None:
    data = [item for item in cycle() if item.entities[STATE].state != "auto_emptying"]
    model = candidate(data)
    assert not any(branch.activity == "auto_emptying" for branch in model.branches)
    item = sample("auto_emptying", 600)
    assert model.estimate_power(item) is None
    assert model.estimate_power(sample("sleeping", 3.5)) == 3.5


def test_missing_battery_before_a_later_branch_matches_export() -> None:
    model = candidate()
    sleeping = sample("sleeping", 3.5)
    assert (
        model.estimate_power(
            replace(sleeping, entities={key: value for key, value in sleeping.entities.items() if key != BATTERY})
        )
        is None
    )
    # Higher-priority dock modes do not need the charging source.
    washing = sample("washing", 22)
    assert (
        model.estimate_power(
            replace(washing, entities={key: value for key, value in washing.entities.items() if key != BATTERY})
        )
        == 22
    )
