from dataclasses import replace
import json
from pathlib import Path

from measure.analyser.entity_references import resolve_portable_entity
from measure.analyser.execution import RecorderAnalysisExecution
from measure.analyser.fixed import FixedStatesPowerCandidate
from measure.analyser.models import (
    ActivityReport,
    AnalysisStatus,
    EnergyMetrics,
    FeatureReference,
    FeatureSource,
    RecorderAnalysisResult,
    StrategyNotApplicable,
    TrainingValidationSplit,
    ValidationMethod,
)
from measure.analyser.recording import load_recordings, restore_recording_context
from measure.analyser.sample_intervals import calculate_sample_durations
from measure.analyser.service import RecorderAnalyser
from measure.analyser.vacuum.signals import (
    Activity,
    ActivitySignal,
    discover_signals,
    resolve_activity,
)
from measure.analyser.vacuum.strategy import (
    ChargingBranch,
    ChargingPoint,
    FixedBranch,
    VacuumCompositeCandidate,
    VacuumCompositeStrategy,
    calculate_average_power,
    get_battery_level,
    group_vacuum_episodes,
    split_vacuum_samples,
)
from measure.analyser.vacuum.validation import build_activity_reports, find_credibility_failure
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.recording.models import (
    RecordedEntity,
    RecordedEntityState,
    RecorderProfileRecipe,
    RecordingContext,
    RecordingMetadata,
    RecordingSample,
)
from measure.request import RecorderMeasurementRequest
import pytest

PRIMARY = "vacuum.robot"
BATTERY = "sensor.battery"
STATE = "sensor.activity"
DRYING = "binary_sensor.drying"
CONTEXT = RecordingContext(
    RecorderProfileRecipe.VACUUM_ROBOT,
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


def test_value_seen_only_in_the_held_out_run_is_not_unexplained(tmp_path: Path) -> None:
    """Signals are discovered over every sample, so an alias the held-out run alone uses resolves.

    The split already accepted this recording because it saw both runs. Rediscovering signals
    from the training half would leave that run's away samples matching no known activity, and
    reject the profile asking for a cycle the user had in fact recorded.
    """

    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id=PRIMARY,
        battery_entity_id=BATTERY,
        additional_entity_ids=(STATE, DRYING, "switch.auto_drying"),
    )
    write_recording(tmp_path / "record.jsonl", cycle())
    # The same activity, reported under a second alias the first run never used.
    aliased = [
        replace(item, entities={**item.entities, STATE: RecordedEntityState("sweeping", {})})
        if item.entities[STATE].state == "cleaning"
        else item
        for item in cycle()
    ]
    write_recording(tmp_path / "record-1.jsonl", aliased)

    summary = RecorderAnalysisExecution().run(request, tmp_path)

    assert summary["Recording analysis"] == "Composite vacuum profile created"
    assert "away" in summary["Recorded activities"]


def test_summary_activities_exclude_the_unexplained_bucket(tmp_path: Path) -> None:
    """Tolerated unexplained samples are not a mode the profile covers.

    The analyser accepts a recording with a small share of them, so the summary must not
    list "unexplained" beside the activities it does cover.
    """

    request = RecorderMeasurementRequest(
        power_meter=DummyPowerMeterSpec(),
        recorder_purpose="complex_profile",
        profile_recipe="vacuum_robot",
        vacuum_entity_id=PRIMARY,
        battery_entity_id=BATTERY,
        additional_entity_ids=(STATE, DRYING, "switch.auto_drying"),
    )

    def with_unknown_status(items: list[RecordingSample]) -> list[RecordingSample]:
        # A status no alias table recognises, under the tolerated 10% share.
        extra = [
            replace(
                sample("cleaning", 12.0, len(items) + index),
                entities={
                    **sample("cleaning", 12.0).entities,
                    STATE: RecordedEntityState("error_dustbin_full", {}),
                },
            )
            for index in range(6)
        ]
        return [replace(item, elapsed_seconds=float(index)) for index, item in enumerate(items + extra)]

    write_recording(tmp_path / "record.jsonl", with_unknown_status(cycle()))
    write_recording(tmp_path / "record-1.jsonl", with_unknown_status(cycle()))

    summary = RecorderAnalysisExecution().run(request, tmp_path)

    assert summary["Recording analysis"] == "Composite vacuum profile created"
    assert "unexplained" not in summary["Recorded activities"]
    assert "washing" in summary["Recorded activities"]
    # The bucket stays in the artifact, where it is labelled for diagnostics.
    activities = json.loads((tmp_path / "analyser.json").read_text())["activities"]
    assert any(item["activity"] == "unexplained" for item in activities)


def test_insufficient_result_reports_belong_to_the_reason_it_states(tmp_path: Path) -> None:
    """The stated reason and the activity reports must describe the same candidate.

    Only reachable with injected strategies today, but the reports of a later strategy
    must not be attached to an earlier strategy's rejection.
    """

    class NeverApplicable:
        strategy_id = "never_applicable"

        def build_candidates(
            self,
            samples: list[RecordingSample],
            context: RecordingContext,
            signals: list[ActivitySignal],
            *,
            recording_samples: list[RecordingSample] | None = None,
        ) -> StrategyNotApplicable:
            return StrategyNotApplicable("never_applicable did not fit")

    # Enough unrecognised samples that the vacuum candidate fails its credibility check.
    unknown = [
        replace(
            sample("cleaning", 12.0, index),
            entities={**sample("cleaning", 12.0).entities, STATE: RecordedEntityState("error_dustbin_full", {})},
        )
        for index in range(30)
    ]
    data = [replace(item, elapsed_seconds=float(index)) for index, item in enumerate(repeated() + unknown)]
    path = write_recording(tmp_path / "record.jsonl", data)

    analyser = RecorderAnalyser([NeverApplicable(), VacuumCompositeStrategy()])
    result = analyser.analyse(path, CONTEXT)

    assert not result.model_ready
    assert result.reason == "never_applicable did not fit"
    assert result.activity_reports == []


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


def write_recording(path: Path, samples: list[RecordingSample], context: RecordingContext | None = CONTEXT) -> Path:
    records = [context.build_metadata_record()] if context is not None else []
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
    samples: list[RecordingSample] | None = None, context: RecordingContext = CONTEXT
) -> VacuumCompositeCandidate:
    data = samples if samples is not None else cycle()
    result = VacuumCompositeStrategy().build_candidates(data, context, discover_signals(data, context))
    assert not isinstance(result, StrategyNotApplicable)
    [model] = result
    assert isinstance(model, VacuumCompositeCandidate)
    return model


def test_composite_features_preserve_order_without_duplicates() -> None:
    model = candidate()
    expected = [
        FeatureReference(PRIMARY, FeatureSource.ATTRIBUTE, "auto_empty_status"),
        FeatureReference(PRIMARY, FeatureSource.ATTRIBUTE, "washing"),
        FeatureReference(DRYING, FeatureSource.STATE),
        FeatureReference(STATE, FeatureSource.STATE),
        FeatureReference(BATTERY, FeatureSource.STATE),
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
    assert result.build_summary()["Validation method"] == "held_out_episodes"
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
    assert result.build_summary()["Recording analysis"] == "Composite vacuum profile created"
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
    assert result.build_summary()["Validation method"] == "held_out_recording"
    assert result.metrics is not None
    assert result.metrics.validation_count == len(cycle())
    assert candidate().complexity == 12
    assert candidate().feature == candidate().features[0]


@pytest.mark.parametrize("missing_activity", ["washing", "charging", "drying"])
def test_incomplete_last_recording_falls_back_to_independent_episode_validation(
    tmp_path: Path, missing_activity: str
) -> None:
    first = write_recording(tmp_path / "record-1.jsonl", repeated())
    last = write_recording(
        tmp_path / "record.jsonl", [item for item in cycle() if item.entities[STATE].state != missing_activity]
    )
    samples = load_recordings([first, last]).dataset.samples

    split = split_vacuum_samples(samples, CONTEXT)

    assert isinstance(split, TrainingValidationSplit)
    assert split.method is ValidationMethod.HELD_OUT_EPISODES
    training_ids = {id(item) for item in split.training}
    validation_ids = {id(item) for item in split.validation}
    assert training_ids.isdisjoint(validation_ids)
    assert training_ids | validation_ids == {id(item) for item in samples}
    # Whole episodes stay together; adjacent samples from the same cycle never
    # become each other's validation evidence.
    signals = discover_signals(samples, CONTEXT)
    for episode in group_vacuum_episodes(samples, signals):
        episode_ids = {id(item) for item in episode.samples}
        assert episode_ids <= training_ids or episode_ids <= validation_ids
    expected_activities = {item.entities[STATE].state for item in cycle()}
    assert {item.entities[STATE].state for item in split.training} == expected_activities
    assert {item.entities[STATE].state for item in split.validation} == expected_activities
    assert any(item.recording_id == 1 for item in split.training)
    assert any(item.recording_id == 0 for item in split.validation)

    result = RecorderAnalyser().analyse([first, last], CONTEXT)

    assert result.model_ready
    assert result.validation_method is ValidationMethod.HELD_OUT_EPISODES
    assert result.metrics is not None
    assert result.metrics.coverage == 1
    assert result.metrics.mae_w == 0
    assert result.metrics.validation_count == len(split.validation)


def test_sparse_single_cycle_needs_more_charging_samples(tmp_path: Path) -> None:
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", cycle()), CONTEXT)
    assert not result.model_ready
    assert "three battery ranges" in str(result.reason)


def dense_cycle() -> list[RecordingSample]:
    return [
        replace(item, elapsed_seconds=float(index))
        for index, item in enumerate(item for item in cycle() for _ in range(3))
    ]


def test_one_complete_cycle_can_create_a_profile(tmp_path: Path) -> None:
    samples = dense_cycle()
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", samples), CONTEXT)

    assert result.model_ready
    assert result.validation_method == ValidationMethod.HELD_OUT_BLOCKS
    assert result.metrics is not None
    assert result.metrics.coverage == 1
    assert result.metrics.mae_w == 0
    assert any("repeatability across cycles has not been tested" in warning for warning in result.warnings)
    assert {report.activity for report in result.activity_reports} == {
        Activity.SLEEPING,
        Activity.WASHING,
        Activity.AUTO_EMPTYING,
        Activity.DRYING,
        Activity.CHARGING,
        Activity.AWAY,
    }
    assert all(report.validation_count > 0 for report in result.activity_reports)

    split = split_vacuum_samples(samples, CONTEXT)
    assert isinstance(split, TrainingValidationSplit)
    training_ids = {id(item) for item in split.training}
    validation_ids = {id(item) for item in split.validation}
    assert training_ids.isdisjoint(validation_ids)
    assert training_ids | validation_ids == {id(item) for item in samples}


def test_single_continuous_charge_with_tapering_and_meter_noise(tmp_path: Path) -> None:
    samples = [item for item in dense_cycle() if item.entities[STATE].state != "charging"]
    for level in range(20, 101):
        power = 30 if level < 75 else max(3, 30 - (level - 75) * 1.2)
        for index in range(10):
            samples.append(sample("charging", power + (0.1 if index % 2 else -0.1), len(samples), level))
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", samples), CONTEXT)

    assert result.model_ready
    assert result.validation_method == ValidationMethod.HELD_OUT_BLOCKS
    report = next(report for report in result.activity_reports if report.activity == Activity.CHARGING)
    assert report.coverage == 1
    assert report.mae_w is not None
    assert report.mae_w < 1


def test_repeated_charges_still_check_independent_power_differences(tmp_path: Path) -> None:
    first = write_recording(tmp_path / "record-1.jsonl", dense_cycle())
    different = [
        replace(item, power=item.power * 2) if item.entities[STATE].state == "charging" else item
        for item in dense_cycle()
    ]
    second = write_recording(tmp_path / "record-2.jsonl", different)
    result = RecorderAnalyser().analyse([first, second], CONTEXT)

    assert not result.model_ready
    assert result.validation_method == ValidationMethod.HELD_OUT_RECORDING
    assert "charging validation error" in str(result.reason)


def test_single_cycle_still_rejects_a_bad_fit(tmp_path: Path) -> None:
    samples = dense_cycle()
    washing = [item for item in samples if item.entities[STATE].state == "washing"]
    high_ids = {id(item) for item in washing[8:22]}
    samples = [replace(item, power=100) if id(item) in high_ids else item for item in samples]
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", samples), CONTEXT)

    assert not result.model_ready
    assert "washing validation" in str(result.reason)


@pytest.mark.parametrize("isolated_first", [True, False])
def test_one_isolated_charge_can_supplement_overlapping_recordings(tmp_path: Path, isolated_first: bool) -> None:
    overlapping = [
        replace(item, entities={**item.entities, DRYING: RecordedEntityState("on", {})}, power=7)
        if item.entities[STATE].state == "charging"
        else item
        for item in dense_cycle()
    ]
    recordings = [overlapping, dense_cycle()]
    if isolated_first:
        recordings.reverse()
    paths = [write_recording(tmp_path / f"record-{index}.jsonl", data) for index, data in enumerate(recordings)]

    result = RecorderAnalyser().analyse(paths, CONTEXT)

    assert result.model_ready
    assert result.validation_method == ValidationMethod.HELD_OUT_BLOCKS
    assert next(report for report in result.activity_reports if report.activity == Activity.CHARGING).coverage == 1


def test_drying_overlap_requests_one_isolated_charge(tmp_path: Path) -> None:
    samples = [
        replace(item, entities={**item.entities, DRYING: RecordedEntityState("on", {})}, power=60)
        if item.entities[STATE].state == "charging"
        else item
        for item in dense_cycle()
    ]
    samples.extend(sample("charging", 3, len(samples) + index, 100) for index in range(30))
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", samples), CONTEXT)

    assert not result.model_ready
    assert "Drying overlaps the battery rise" in str(result.reason)
    assert "one continuous charge with mop drying switched off" in str(result.reason)


def test_short_mode_error_is_not_hidden_by_long_idle(tmp_path: Path) -> None:
    data = repeated()
    second_start = len(cycle())
    data = [
        replace(item, power=100) if index >= second_start and item.entities[STATE].state == "washing" else item
        for index, item in enumerate(data)
    ]
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", data), CONTEXT)
    assert not result.model_ready
    assert "washing validation predicts 22.00 W on average, but 100.00 W was measured" in str(result.reason)
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
    assert model.features.count(FeatureReference(DRYING, FeatureSource.STATE)) == 1


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
        ActivitySignal(
            Activity.WASHING, FeatureReference(PRIMARY, FeatureSource.ATTRIBUTE, "washing"), [True], [False]
        ).matches(replace(item, entities={**item.entities, PRIMARY: replace(primary, attributes={"washing": 1})}))
        is None
    )


@pytest.mark.parametrize("level", ["unknown", "unavailable", "bad", True, -1, 101, "NaN", "inf"])
def test_invalid_battery_levels(level: object) -> None:
    item = sample("charging", 10, level=level)
    feature = FeatureReference(PRIMARY, FeatureSource.ATTRIBUTE, "battery_level")
    assert get_battery_level(item, feature) is None
    assert candidate().estimate_power(item) is None


def test_charging_range_integer_conversion_and_attribute_fallback() -> None:
    model = candidate()
    assert model.estimate_power(sample("charging", 0, level="45.9")) == 27.5
    assert model.estimate_power(sample("charging", 0, level=19)) is None
    assert model.estimate_power(sample("charging", 0, level=81)) is None
    bare = replace(CONTEXT, entities=[RecordedEntity(e.entity_id, e.domain, e.role) for e in CONTEXT.entities])
    model = candidate(context=bare)
    assert model.battery == FeatureReference(PRIMARY, FeatureSource.ATTRIBUTE, "battery_level")
    fragment = model.build_model_config_fragment().to_dict()
    charging = next(branch for branch in fragment["composite_config"]["strategies"] if "linear" in branch)
    assert charging["entity_id"] == "[[entity]]"
    assert charging["linear"]["attribute"] == "battery_level"
    assert get_battery_level(sample("charging", 1), None) is None


@pytest.mark.parametrize(
    "levels,reason", [([20, 25, 30], "20 battery"), ([20, 50, 80], "coverage gap"), ([20, 80], "three battery")]
)
def test_unsupported_charging_curves(levels: list[int], reason: str) -> None:
    data = [sample("sleeping", 3.5, index) for index in range(5)]
    data += [sample("charging", 20, len(data) + index, level) for level in levels for index in range(3)]
    result = VacuumCompositeStrategy().build_candidates(data, CONTEXT, discover_signals(data, CONTEXT))
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
    result = VacuumCompositeStrategy().build_candidates(data, bare, discover_signals(data, bare))
    assert isinstance(result, StrategyNotApplicable)
    assert "portable battery metadata" in result.reason


def test_portable_references_require_unique_same_device_metadata() -> None:
    assert resolve_portable_entity(PRIMARY, CONTEXT) == "[[entity]]"
    assert resolve_portable_entity(STATE, CONTEXT) == "[[entity_by_translation_key:state]]"
    assert resolve_portable_entity("sensor.missing", CONTEXT) is None
    duplicate = RecordedEntity(
        "sensor.duplicate", "sensor", "disabled", translation_key="state", device_id="robot", disabled_by="user"
    )
    assert resolve_portable_entity(STATE, replace(CONTEXT, device_entities=[*CONTEXT.entities, duplicate])) is None
    other = replace(CONTEXT.entities[2], device_id="other")
    assert resolve_portable_entity(STATE, replace(CONTEXT, entities=[*CONTEXT.entities[:2], other])) is None
    duplicate_battery = replace(duplicate, translation_key=None, device_class="battery")
    assert (
        resolve_portable_entity(BATTERY, replace(CONTEXT, device_entities=[*CONTEXT.entities, duplicate_battery]))
        is None
    )


def test_telemetry_gaps_are_not_independent_cycles() -> None:
    first = sample("sleeping", 3.5)
    data = [
        first,
        replace(first, elapsed_seconds=31),
        replace(first, elapsed_seconds=32),
        replace(first, recording_id=1, elapsed_seconds=0),
        replace(first, recording_id=1, elapsed_seconds=0),
    ]
    episodes = group_vacuum_episodes(data, discover_signals(data, CONTEXT))
    assert [len(episode.samples) for episode in episodes] == [3, 2]
    assert group_vacuum_episodes([], []) == []


def test_unexplained_episodes_are_held_out_and_reported(tmp_path: Path) -> None:
    data = repeated() + [sample("unrecognised_mode", 20, len(repeated()) + index) for index in range(20)]
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", data), CONTEXT)
    assert not result.model_ready
    assert "20 of 162 samples match no known activity" in str(result.reason)
    assert result.to_dict()["activities"][-1]["activity"] == "unexplained"
    assert result.activity_reports[-1].mae_w is None
    assert result.activity_reports[-1].activity is None


def test_brief_unexplained_blip_does_not_reject_recording(tmp_path: Path) -> None:
    data = repeated()
    data[15] = replace(sample("unrecognised_mode", 22), elapsed_seconds=data[15].elapsed_seconds)
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", data), CONTEXT)
    assert result.model_ready
    assert None in {report.activity for report in result.activity_reports}


def test_energy_only_integrates_adjacent_held_out_samples() -> None:
    data = repeated()
    model = candidate()
    reports = build_activity_reports(model, data, [data[0], data[2], replace(data[3], recording_id=99)])
    assert all(report.energy.duration_seconds == 0 for report in reports)
    assert all(report.energy.bias_percent is None for report in reports)
    assert find_credibility_failure(reports) is not None


def test_strategy_rejections_and_empty_recordings(tmp_path: Path) -> None:
    strategy = VacuumCompositeStrategy()

    def build(data: list[RecordingSample], context: RecordingContext = CONTEXT) -> object:
        return strategy.build_candidates(data, context, discover_signals(data, context))

    assert isinstance(build(cycle(), replace(CONTEXT, recipe=RecorderProfileRecipe.GENERIC)), StrategyNotApplicable)
    assert isinstance(build([sample("sleeping", 3.5)] * 10), StrategyNotApplicable)
    result = build([replace(item, power=-1) for item in cycle()])
    assert isinstance(result, StrategyNotApplicable)
    assert "non-negative" in result.reason
    assert isinstance(build([sample("sleeping", 3)] * 5 + [sample("washing", 22)]), StrategyNotApplicable)
    assert isinstance(split_vacuum_samples([sample("mystery", 1)] * 20, CONTEXT), StrategyNotApplicable)
    result = RecorderAnalyser().analyse(write_recording(tmp_path / "record.jsonl", []), CONTEXT)
    assert not result.model_ready


def test_metadata_validation_and_legacy_loading(tmp_path: Path) -> None:
    path = write_recording(tmp_path / "first.jsonl", cycle())
    different = write_recording(
        tmp_path / "second.jsonl", cycle(), replace(CONTEXT, recipe=RecorderProfileRecipe.GENERIC)
    )
    with pytest.raises(ValueError, match="same recipe"):
        load_recordings([path, different])
    with pytest.raises(ValueError, match="at least one"):
        load_recordings([])
    legacy = write_recording(tmp_path / "legacy.jsonl", cycle(), None)
    assert load_recordings([legacy]).dataset.metadata is None
    assert restore_recording_context(CONTEXT, None) == CONTEXT
    assert restore_recording_context(CONTEXT, RecordingMetadata("generic", None)) == CONTEXT
    metadata_path = tmp_path / "metadata.jsonl"
    metadata_path.write_text(
        json.dumps(
            {
                "record_type": "metadata",
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
                "related_device_ids": ["dock", 5],
            }
        ),
        encoding="utf-8",
    )
    enriched = restore_recording_context(CONTEXT, load_recordings([metadata_path]).dataset.metadata)
    assert enriched.related_device_ids == ["dock"]
    assert enriched.entities[0].role == "primary"
    assert enriched.entities[0].device_id == "new"
    assert enriched.entities[0].unit is None
    assert enriched.entities[0].has_live_state is True


def test_report_serialization() -> None:
    fixed = FixedStatesPowerCandidate(FeatureReference(PRIMARY, FeatureSource.STATE), {"docked": 3, "cleaning": 0.3})
    assert fixed.features == [fixed.feature]
    result = RecorderAnalysisResult(
        AnalysisStatus.INSUFFICIENT_DATA,
        10,
        validation_method=ValidationMethod.HELD_OUT_RECORDING,
        activity_reports=build_activity_reports(candidate(), repeated(), cycle()),
    )
    assert result.to_dict()["validation_method"] == "held_out_recording"
    assert "activities" in result.to_dict()
    assert resolve_activity(sample("sleeping", 3.5), ()) is None
    assert FixedBranch(Activity.AWAY, 0.3).estimate(sample("cleaning", 0.3), None) == 0.3


def test_activity_report_preserves_flat_json_contract() -> None:
    report = ActivityReport(
        activity=Activity.WASHING,
        sample_count=20,
        episode_count=2,
        validation_count=10,
        coverage=1,
        mae_w=0.2,
        transition_mae_w=0.4,
        mean_power_w=22,
        energy=EnergyMetrics(duration_seconds=9, measured_wh=0.055, predicted_wh=0.056, bias_percent=1.82),
    )
    result = RecorderAnalysisResult(AnalysisStatus.INSUFFICIENT_DATA, 20, activity_reports=[report])
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
    branch = ChargingBranch(
        calibration=[
            ChargingPoint(battery_level=20, power=40),
            ChargingPoint(battery_level=40, power=30),
            ChargingPoint(battery_level=80, power=10),
        ],
    )
    battery = FeatureReference(BATTERY, FeatureSource.STATE)
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


def test_export_preserves_unmeasured_auto_empty_guard_without_fitting_its_power() -> None:
    data = [item for item in cycle() if item.entities[STATE].state != "auto_emptying"]
    fragment = candidate(data).build_model_config_fragment().to_dict()
    strategies = fragment["composite_config"]["strategies"]

    assert len(strategies) == 5
    assert not any(branch.get("fixed", {}).get("power") == 600 for branch in strategies)
    assert all("auto_empty_status" in json.dumps(branch["condition"]) for branch in strategies)


def test_profile_without_charging_uses_only_activity_features() -> None:
    data = [sample("cleaning", 0.3)] * 10 + [sample("washing", 22)] * 10
    model = candidate(data)

    assert model.battery is None
    assert FeatureReference(BATTERY, FeatureSource.STATE) not in model.features
    assert all(isinstance(branch, FixedBranch) for branch in model.branches)
    assert model.estimate_power(sample("cleaning", 0)) == 0.3
    assert model.estimate_power(sample("washing", 0)) == 22
    fragment = model.build_model_config_fragment().to_dict()
    assert len(fragment["composite_config"]["strategies"]) == 2
    assert "linear" not in json.dumps(fragment)


def test_unidentified_training_activity_does_not_distort_fitted_branches() -> None:
    unidentified = sample("new_mode", 999)
    model = candidate([*cycle(), unidentified])

    assert model.estimate_power(unidentified) is None
    assert model.build_model_config_fragment() == candidate().build_model_config_fragment()


@pytest.mark.parametrize("level", ["bad", "unknown", "unavailable"])
def test_invalid_training_battery_samples_do_not_distort_charging_curve(level: str) -> None:
    invalid = sample("charging", 999, level=level)
    model = candidate([*cycle(), invalid])

    assert model.estimate_power(invalid) is None
    assert model.build_model_config_fragment() == candidate().build_model_config_fragment()


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


def test_fixed_branch_preserves_energy_of_a_cycling_load() -> None:
    # A dryer heater cycling on and off: the median would report the heater-on level.
    heater = iter([120, 120, 10] * 3 + [120])
    data = [replace(item, power=next(heater)) if item.entities[STATE].state == "drying" else item for item in cycle()]

    branches = {branch.activity: branch for branch in candidate(data).branches}

    assert branches[Activity.DRYING].power == 83.33


def test_average_power_weights_readings_by_the_time_they_represent() -> None:
    held = sample("drying", 100, 0)
    short_reading = replace(sample("drying", 10, 2), elapsed_seconds=2.0)
    long_reading = replace(sample("drying", 40, 6), elapsed_seconds=6.0)
    before_last = replace(sample("drying", 1000, 100), elapsed_seconds=100.0)
    next_recording = replace(sample("drying", 1000, 0), recording_id=1)
    data = [held, short_reading, long_reading, before_last, next_recording]

    durations = calculate_sample_durations(data, data)

    # Each endpoint gets half the interval, excluding long gaps and recording boundaries.
    assert list(durations.values()) == [1.0, 3.0, 2.0]
    assert calculate_average_power(data, durations) == 35.0
    assert calculate_average_power([before_last, next_recording], durations) == 1000.0


def test_held_out_recording_must_cover_a_meaningful_share_of_each_activity() -> None:
    # The first recording charges ten times longer, leaving the second only about 9% of charging.
    long_charge = [item for item in cycle() for _ in range(10 if item.entities[STATE].state == "charging" else 1)]
    first = [replace(item, elapsed_seconds=float(index)) for index, item in enumerate(long_charge)]
    second = [replace(item, recording_id=1) for item in cycle()]

    split = split_vacuum_samples(first + second, CONTEXT)

    assert isinstance(split, TrainingValidationSplit)
    assert split.method is ValidationMethod.HELD_OUT_EPISODES


def test_fixed_power_activities_are_validated_on_energy() -> None:
    data = repeated()
    split = split_vacuum_samples(data, CONTEXT)
    assert isinstance(split, TrainingValidationSplit)
    candidates = VacuumCompositeStrategy().build_candidates(
        split.training, CONTEXT, split.signals, recording_samples=data
    )
    assert not isinstance(candidates, StrategyNotApplicable)
    [model] = candidates
    assert isinstance(model, VacuumCompositeCandidate)
    reports = build_activity_reports(model, data, split.validation)
    assert find_credibility_failure(reports) is None
    for report in reports:
        assert report.energy.duration_seconds > 0
        assert report.energy.measured_wh > 0
        assert report.energy.predicted_wh == pytest.approx(report.energy.measured_wh, abs=0.0001)
    assert {report.activity for report in reports if report.has_fixed_power} == {
        "sleeping",
        "washing",
        "auto_emptying",
        "drying",
        "away",
    }


def activity_report(
    mae_w: float,
    measured_wh: float,
    predicted_wh: float,
    duration_seconds: float = 3600,
    coverage: float = 1,
    has_fixed_power: bool = True,
) -> ActivityReport:
    return ActivityReport(
        activity=Activity.DRYING if has_fixed_power else Activity.CHARGING,
        sample_count=100,
        episode_count=2,
        validation_count=50,
        coverage=coverage,
        mae_w=mae_w,
        transition_mae_w=None,
        mean_power_w=measured_wh,
        energy=EnergyMetrics(duration_seconds, measured_wh, predicted_wh, None),
        has_fixed_power=has_fixed_power,
    )


@pytest.mark.parametrize(
    "report,expected",
    [
        # A cycling heater: large per-sample error, but the fixed power holds its energy.
        (activity_report(mae_w=50, measured_wh=66, predicted_wh=62), None),
        (activity_report(mae_w=5, measured_wh=88, predicted_wh=62), "predicts 62.00 W on average, but 88.00 W"),
        # Below the absolute allowance, a large relative error is still negligible.
        (activity_report(mae_w=0.3, measured_wh=0.6, predicted_wh=1.0), None),
        (activity_report(mae_w=0, measured_wh=0, predicted_wh=0, duration_seconds=0), "no consecutive readings"),
        (activity_report(mae_w=0, measured_wh=66, predicted_wh=66, coverage=0.5), "cannot reliably identify drying"),
        (
            activity_report(mae_w=0, measured_wh=30, predicted_wh=30, coverage=0.25, has_fixed_power=False),
            "charging model covers only 25% of its validation samples",
        ),
        # A charging curve should follow each reading, so it keeps the per-sample check.
        (
            activity_report(mae_w=10, measured_wh=30, predicted_wh=30, has_fixed_power=False),
            "charging validation error",
        ),
        (activity_report(mae_w=1, measured_wh=30, predicted_wh=20, has_fixed_power=False), None),
    ],
)
def test_activity_validation(report: ActivityReport, expected: str | None) -> None:
    failure = find_credibility_failure([report])
    if expected is None:
        assert failure is None
    else:
        assert failure is not None
        assert expected in failure


@pytest.mark.parametrize("separate_recordings", [False, True])
def test_identical_irregular_cycles_pass_energy_validation(tmp_path: Path, separate_recordings: bool) -> None:
    first = [
        sample("drying", power, time) for power, time in zip([0, 0, 0, 0, 100, 0], [0, 1, 2, 3, 4, 24], strict=True)
    ]
    first.extend(sample("sleeping", 3.5, time) for time in range(25, 35))
    if separate_recordings:
        paths = [write_recording(tmp_path / "first.jsonl", first), write_recording(tmp_path / "second.jsonl", first)]
    else:
        second = [replace(item, elapsed_seconds=item.elapsed_seconds + 35) for item in first]
        paths = [write_recording(tmp_path / "cycles.jsonl", first + second)]
    result = RecorderAnalyser().analyse(paths, CONTEXT)
    assert result.model_ready, result.reason
    drying = next(report for report in result.activity_reports if report.activity == "drying")
    assert drying.energy.duration_seconds == 24
    assert drying.energy.measured_wh == pytest.approx(1050 / 3600, abs=0.0001)
    assert drying.energy.predicted_wh == drying.energy.measured_wh


def test_training_does_not_bridge_excluded_samples() -> None:
    data = [sample("drying", 10, index) for index in range(5)]
    data.extend(sample("sleeping", 3.5, index) for index in range(5, 10))
    data.extend(sample("drying", 100, index) for index in range(10, 15))
    data.extend(sample("sleeping", 3.5, index) for index in range(15, 20))
    training = data[:5] + data[10:]
    candidates = VacuumCompositeStrategy().build_candidates(
        training, CONTEXT, discover_signals(data, CONTEXT), recording_samples=data
    )
    assert not isinstance(candidates, StrategyNotApplicable)
    [model] = candidates
    assert isinstance(model, VacuumCompositeCandidate)
    drying = next(branch for branch in model.branches if branch.activity == Activity.DRYING)
    assert drying.power == 55


def test_time_weights_ignore_non_increasing_timestamps() -> None:
    data = [sample("drying", 10, time) for time in [1, 1, 0]]
    assert calculate_sample_durations(data, data) == {}


@pytest.mark.parametrize("training_power, accepted", [(1.49, True), (1.51, False)])
def test_short_activity_validation_uses_unrounded_energy(tmp_path: Path, training_power: float, accepted: bool) -> None:
    paths = []
    for index, power in enumerate([training_power, 1.0]):
        data = [sample("sleeping", power, second) for second in range(5)]
        data.extend(sample("washing", 100, second) for second in range(5, 10))
        paths.append(write_recording(tmp_path / f"record-{index}.jsonl", data))

    result = RecorderAnalyser().analyse(paths, CONTEXT)

    assert result.model_ready is accepted, result.reason
    sleeping = next(report for report in result.activity_reports if report.activity == "sleeping")
    assert sleeping.energy.measured_wh == pytest.approx(4 / 3600)
    assert sleeping.energy.predicted_wh == pytest.approx(training_power * 4 / 3600)
    assert sleeping.energy.to_dict()["measured_energy_wh"] == 0.0011


@pytest.mark.parametrize("levels", [[], [20], [20, 20], [40, 20]])
def test_charging_curve_rejects_insufficient_or_unordered_points(levels: list[int]) -> None:
    with pytest.raises(ValueError, match="calibration"):
        ChargingBranch([ChargingPoint(level, 30) for level in levels])


@pytest.mark.parametrize(
    "header, expected_recipe, expected_primary",
    [
        ({}, None, None),
        ({"recipe": 8, "primary_entity_id": []}, None, None),
        ({"recipe": "future_recipe", "primary_entity_id": "vacuum.other"}, "future_recipe", "vacuum.other"),
    ],
)
def test_partial_and_unknown_metadata_keeps_samples_readable(
    tmp_path: Path, header: dict[str, object], expected_recipe: str | None, expected_primary: str | None
) -> None:
    path = write_recording(tmp_path / "record.jsonl", cycle(), None)
    path.write_text(json.dumps({"record_type": "metadata", **header}) + "\n" + path.read_text(), encoding="utf-8")

    loaded = load_recordings([path])

    assert loaded.warnings == []
    assert loaded.dataset.samples == cycle()
    metadata = loaded.dataset.metadata
    assert metadata is not None
    assert metadata.recipe == expected_recipe
    assert metadata.primary_entity_id == expected_primary
    assert metadata.entities == []
    assert restore_recording_context(CONTEXT, metadata) is CONTEXT


def test_combining_recordings_preserves_unknown_recipe_identity(tmp_path: Path) -> None:
    paths = []
    for index, recipe in enumerate(["future_recipe", "another_recipe"]):
        path = tmp_path / f"record-{index}.jsonl"
        path.write_text(json.dumps({"record_type": "metadata", "recipe": recipe}), encoding="utf-8")
        paths.append(path)

    with pytest.raises(ValueError, match="same recipe"):
        load_recordings(paths)
