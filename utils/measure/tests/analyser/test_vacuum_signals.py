"""Integration-specific runtime labels without device-name guessing."""

from dataclasses import replace

from measure.analyser.entity_references import resolve_portable_entity
from measure.analyser.vacuum_signals import (
    ALIASES,
    Activity,
    discover_signals,
    resolve_activity,
    suggest_recording_entities,
)
from measure.recording.models import (
    RecordedEntity,
    RecordedEntityState,
    RecorderProfileRecipe,
    RecordingContext,
    RecordingSample,
)
import pytest

PRIMARY = "vacuum.robot"


def context(*entities: RecordedEntity) -> RecordingContext:
    return RecordingContext(
        RecorderProfileRecipe.VACUUM_ROBOT,
        PRIMARY,
        "vacuum_robot",
        [
            RecordedEntity(PRIMARY, "vacuum", "primary", device_id="robot"),
            *entities,
        ],
    )


def entity(key: str, domain: str = "sensor", integration: str = "dreame_vacuum") -> RecordedEntity:
    return RecordedEntity(
        domain + "." + key, domain, "tracked", device_id="robot", translation_key=key, integration=integration
    )


def sample(state: str = "docked", **states: str) -> RecordingSample:
    return RecordingSample(
        0,
        5,
        {
            PRIMARY: RecordedEntityState(state, {}),
            **{key: RecordedEntityState(value, {}) for key, value in states.items()},
        },
    )


def test_suggest_roborock_activity_entities() -> None:
    ctx = context(
        entity("status", integration="roborock"),
        *[
            replace(entity(key, "switch", "roborock"), device_id="dock")
            for key in ["mop_washing", "mop_drying", "dust_emptying"]
        ],
        replace(entity("mop_drying_status", "binary_sensor", "roborock"), device_id="dock"),
        entity("mop_drying_remaining_time", integration="roborock"),
        entity("in_cleaning", "binary_sensor", "roborock"),
        replace(
            entity("battery_charging", "binary_sensor", "roborock"),
            translation_key=None,
            device_class="battery_charging",
        ),
        entity("child_lock", "switch", "roborock"),
        entity("routine", "button", "roborock"),
        entity("cleaning_mode", "select", "roborock"),
        replace(entity("status", integration="powercalc"), entity_id="sensor.estimated_power", device_id="other"),
        replace(entity("mop_washing", "switch", "roborock"), entity_id="switch.other_robot_wash", device_id="other"),
    )
    ctx = replace(ctx, related_device_ids=["dock"])
    suggestions = suggest_recording_entities(ctx)
    assert suggestions.selected == ["sensor.status", "switch.mop_washing", "switch.mop_drying", "switch.dust_emptying"]
    assert suggestions.disabled == []


@pytest.mark.parametrize("disabled_by,has_live_state", [("user", False), (None, False)])
def test_suggest_deprecated_drying_fallback(disabled_by: str | None, has_live_state: bool) -> None:
    ctx = context(
        replace(entity("mop_drying", "switch"), disabled_by=disabled_by, has_live_state=has_live_state),
        entity("mop_drying_status", "binary_sensor", "roborock"),
    )
    suggestions = suggest_recording_entities(ctx)
    assert suggestions.selected == ["binary_sensor.mop_drying_status"]
    assert suggestions.disabled == (["switch.mop_drying"] if disabled_by else [])


def test_suggest_supported_signals_across_integrations() -> None:
    ctx = context(
        entity("state"),
        entity("status"),
        entity("station_state"),
        entity("self_wash_base_status"),
        entity("auto_empty_status"),
        entity("charging_status"),
        entity("charging_state", "binary_sensor"),
        replace(entity("charging", "binary_sensor", "ecovacs"), translation_key=None, device_class="battery_charging"),
        entity("auto_drying", "switch"),
    )
    assert suggest_recording_entities(ctx).selected == [
        "sensor.state",
        "sensor.status",
        "sensor.station_state",
        "sensor.self_wash_base_status",
        "sensor.auto_empty_status",
        "sensor.charging_status",
        "binary_sensor.charging_state",
        "binary_sensor.charging",
    ]


def test_suggestions_require_unambiguous_portable_references() -> None:
    ctx = context(
        entity("status"),
        replace(entity("status"), entity_id="sensor.duplicate_status", disabled_by="user"),
        replace(entity("mop_drying", "switch"), device_id="dock"),
        replace(entity("mop_drying", "switch"), entity_id="switch.second_dock_drying", device_id="second_dock"),
        entity("state", integration="powercalc"),
    )
    ctx = replace(ctx, related_device_ids=["dock", "second_dock"])
    assert suggest_recording_entities(ctx).selected == []


@pytest.mark.parametrize("key,domain", [("mop_drying", "switch"), ("drying", "switch"), ("drying", "binary_sensor")])
@pytest.mark.parametrize("disabled_by", [None, "user"])
def test_deprecated_signal_is_not_suggested_when_same_activity_exists(
    key: str, domain: str, disabled_by: str | None
) -> None:
    ctx = context(
        entity(key, domain), replace(entity("mop_drying_status", "binary_sensor", "roborock"), disabled_by=disabled_by)
    )
    suggestions = suggest_recording_entities(ctx)
    assert suggestions.selected == [f"{domain}.{key}"]
    assert suggestions.disabled == []


def test_other_activity_does_not_replace_deprecated_signal() -> None:
    ctx = context(entity("mop_washing", "switch"), entity("mop_drying_status", "binary_sensor", "roborock"))
    assert suggest_recording_entities(ctx).selected == ["switch.mop_washing", "binary_sensor.mop_drying_status"]


@pytest.mark.parametrize(
    "activity,label", [(activity, label) for activity, labels in ALIASES.items() for label in sorted(labels)]
)
def test_runtime_aliases(activity: Activity, label: str) -> None:
    item = sample(**{"sensor.status": label})
    assert resolve_activity(item, discover_signals([item], context(entity("status")))) is activity


@pytest.mark.parametrize(
    "state,activity",
    [
        ("cleaning", "away"),
        ("returning", "away"),
        ("idle", "away"),
        ("paused", "away"),
        ("docked", "docked"),
        ("error", None),
    ],
)
def test_standard_ha_activities(state: str, activity: str | None) -> None:
    item = sample(state)
    assert resolve_activity(item, discover_signals([item], context())) == activity


def test_dreame_state_wins_over_limited_charging_status_and_status() -> None:
    ctx = context(entity("charging_status"), entity("status"), entity("state"))
    items = [
        sample(**{"sensor.state": state, "sensor.charging_status": charging, "sensor.status": status})
        for state, charging, status in [
            ("washing", "not_charging", "standby"),
            ("charging", "charging", "charging"),
            ("charging_completed", "charging_completed", "standby"),
        ]
    ]
    signals = discover_signals(items, ctx)
    assert [resolve_activity(item, signals) for item in items] == ["washing", "charging", "completed"]
    assert {signal.feature.entity_id for signal in signals} == {"sensor.state"}


@pytest.mark.parametrize(
    "key,states,expected",
    [
        (
            "station_state",
            ["idle", "emptying_dustbin", "washing_mop", "drying_mop"],
            ["docked", "auto_emptying", "washing", "drying"],
        ),
        (
            "self_wash_base_status",
            ["idle", "washing", "drying", "clean_add_water", "adding_water", "returning", "paused"],
            ["docked", "washing", "drying", "washing", "washing", "docked", None],
        ),
        ("auto_empty_status", ["idle", "active", "not_performed"], ["docked", "auto_emptying", "docked"]),
        (
            "charging_status",
            ["not_charging", "charging", "charging_completed", "return_to_charge"],
            ["docked", "charging", "completed", "docked"],
        ),
    ],
)
def test_auxiliary_sensors(key: str, states: list[str], expected: list[str | None]) -> None:
    items = [sample(**{"sensor." + key: state}) for state in states]
    signals = discover_signals(items, context(entity(key)))
    assert [resolve_activity(item, signals) for item in items] == expected
    for state in ("unknown", "unavailable", "new_unmapped_state"):
        assert resolve_activity(sample(**{"sensor." + key: state}), signals) is None


def test_idle_station_preserves_cleaning_and_uses_one_guard() -> None:
    items = [sample(state, **{"sensor.station_state": "idle"}) for state in ("docked", "cleaning")]
    signals = discover_signals(items, context(entity("station_state", integration="ecovacs")))
    assert [resolve_activity(item, signals) for item in items] == ["docked", "away"]
    assert sum(signal.feature.entity_id == "sensor.station_state" for signal in signals) == 1
    assert not any(
        signal.feature.entity_id == "sensor.station_state"
        for signal in discover_signals(
            [sample(**{"sensor.station_state": "unknown"})], context(entity("station_state"))
        )
    )


def test_partial_charging_enum_supplements_completion_only() -> None:
    items = [
        sample(**{"sensor.state": state, "sensor.charging_status": charge})
        for state, charge in [("charging", "charging"), ("docked", "charging_completed"), ("cleaning", "not_charging")]
    ]
    signals = discover_signals(items, context(entity("state"), entity("charging_status")))
    assert [resolve_activity(item, signals) for item in items] == ["charging", "completed", "away"]


@pytest.mark.parametrize("attribute", [True, False])
def test_sleeping_supplements_completed(attribute: bool) -> None:
    ctx = context(entity("state"), entity("status"))
    items = [
        sample(**{"sensor.state": "charging_completed", "sensor.status": status}) for status in ("sleeping", "standby")
    ]
    if attribute:
        ctx = context(entity("state"))
        items = [
            replace(
                item,
                entities={
                    **item.entities,
                    PRIMARY: RecordedEntityState("docked", {"status": item.entities["sensor.status"].state}),
                },
            )
            for item in items
        ]
    signals = discover_signals(items, ctx)
    assert [resolve_activity(item, signals) for item in items] == ["sleeping", "completed"]


@pytest.mark.parametrize(
    "key,domain,integration,device_class,expected",
    [
        ("charging_state", "binary_sensor", "dreame_vacuum", None, ["charging", "docked"]),
        ("battery_charging", "binary_sensor", "ecovacs", "battery_charging", ["charging", "docked"]),
        ("battery_charging", "binary_sensor", "roborock", "battery_charging", ["docked", "docked"]),
        ("mop_drying", "switch", "roborock", None, ["drying", "docked"]),
        ("auto_drying", "switch", "dreame_vacuum", None, ["docked", "docked"]),
        ("water_mop_attached", "binary_sensor", "ecovacs", None, ["docked", "docked"]),
    ],
)
def test_runtime_flags_not_settings(
    key: str, domain: str, integration: str, device_class: str | None, expected: list[str]
) -> None:
    descriptor = replace(
        entity(key, domain, integration), device_class=device_class, translation_key=None if device_class else key
    )
    items = [sample(**{descriptor.entity_id: value}) for value in ("on", "off")]
    signals = discover_signals(items, context(descriptor))
    assert [resolve_activity(item, signals) for item in items] == expected


def test_unrelated_device_is_not_portable() -> None:
    descriptor = replace(entity("mop_drying", "switch", "roborock"), device_id="dock")
    ctx = context(descriptor)
    assert resolve_portable_entity(descriptor.entity_id, ctx) is None
    item = sample(**{descriptor.entity_id: "on"})
    assert resolve_activity(item, discover_signals([item], ctx)) == "docked"


def test_related_dock_entity_is_a_portable_activity_signal() -> None:
    drying = replace(entity("mop_drying", "switch", "roborock"), device_id="dock")
    ctx = replace(context(drying), related_device_ids=["dock"])
    assert resolve_portable_entity(drying.entity_id, ctx) == "[[entity_by_translation_key:mop_drying]]"

    items = [sample(**{drying.entity_id: value}) for value in ("on", "off")]
    signals = discover_signals(items, ctx)
    assert [resolve_activity(item, signals) for item in items] == ["drying", "docked"]
    assert signals[0].build_condition(ctx) == {
        "condition": "state",
        "entity_id": "[[entity_by_translation_key:mop_drying]]",
        "state": ["on"],
    }


def test_drying_switch_wins_over_deprecated_drying_status() -> None:
    switch = replace(entity("mop_drying", "switch", "roborock"), device_id="dock")
    status = replace(entity("mop_drying_status", "binary_sensor", "roborock"), device_id="dock")
    ctx = replace(context(switch, status), related_device_ids=["dock"])
    # A stale deprecated sensor must not decide drying while the switch is available.
    items = [
        sample(**{switch.entity_id: "on", status.entity_id: "off"}),
        sample(**{switch.entity_id: "off", status.entity_id: "on"}),
    ]

    signals = discover_signals(items, ctx)

    assert [signal.feature.entity_id for signal in signals if signal.activity == "drying"] == [switch.entity_id]
    assert [resolve_activity(item, signals) for item in items] == ["drying", "docked"]


def test_deprecated_drying_status_is_used_without_the_switch() -> None:
    status = replace(entity("mop_drying_status", "binary_sensor", "roborock"), device_id="dock")
    ctx = replace(context(status), related_device_ids=["dock"])
    items = [sample(**{status.entity_id: value}) for value in ("on", "off")]

    signals = discover_signals(items, ctx)

    assert [resolve_activity(item, signals) for item in items] == ["drying", "docked"]


@pytest.mark.parametrize(
    "other_device_id",
    [
        # PowerCalc resolves the key to the vacuum's own entity first.
        "robot",
        # PowerCalc refuses a key that matches on more than one related device.
        "second_dock",
    ],
)
def test_related_entity_needs_a_placeholder_resolving_to_it(other_device_id: str) -> None:
    drying = replace(entity("mop_drying", "switch", "roborock"), device_id="dock")
    other = replace(drying, entity_id="switch.other_mop_drying", device_id=other_device_id)
    ctx = replace(context(drying, other), related_device_ids=["dock", "second_dock"])
    assert resolve_portable_entity(drying.entity_id, ctx) is None


def test_related_battery_uses_device_class_when_the_vacuum_has_none() -> None:
    battery = RecordedEntity(
        "sensor.dock_battery", "sensor", "battery", device_class="battery", unit="%", device_id="dock"
    )
    ctx = replace(context(battery), related_device_ids=["dock"])
    assert resolve_portable_entity(battery.entity_id, ctx) == "[[entity_by_device_class:battery]]"


def test_disabled_sleep_status_is_ignored() -> None:
    items = [sample(**{"sensor.state": "charging_completed", "sensor.status": "sleeping"})]
    signals = discover_signals(items, context(entity("state"), replace(entity("status"), disabled_by="user")))
    assert resolve_activity(items[0], signals) == "completed"


def test_unavailable_action_sensor_does_not_override_standard_vacuum_activities() -> None:
    descriptor = entity("mop_drying", "switch", "roborock")
    items = [
        sample("docked", **{descriptor.entity_id: "unavailable"}),
        sample("cleaning", **{descriptor.entity_id: "unknown"}),
    ]

    signals = discover_signals(items, context(descriptor))

    assert all(signal.feature.entity_id != descriptor.entity_id for signal in signals)
    assert [resolve_activity(item, signals) for item in items] == [Activity.DOCKED, Activity.AWAY]


def test_numeric_action_attributes_are_not_interpreted_as_boolean_flags() -> None:
    items = [
        RecordingSample(
            index,
            5,
            {PRIMARY: RecordedEntityState(state, {"drying": value})},
        )
        for index, (state, value) in enumerate([("docked", 0), ("cleaning", 1)])
    ]

    signals = discover_signals(items, context())

    assert all(signal.feature.attribute != "drying" for signal in signals)
    assert [resolve_activity(item, signals) for item in items] == [Activity.DOCKED, Activity.AWAY]
