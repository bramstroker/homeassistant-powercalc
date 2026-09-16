"""Integration-specific runtime labels without device-name guessing."""

from dataclasses import replace

from measure.analyser.models import AnalysisContext, RecordedEntity, RecordedEntityState, RecordingSample
from measure.analyser.vacuum_signals import ALIASES, Activity, discover_signals, portable_entity, resolve_activity
import pytest

PRIMARY = "vacuum.robot"


def context(*entities: RecordedEntity) -> AnalysisContext:
    return AnalysisContext(
        "vacuum_robot",
        PRIMARY,
        "vacuum_robot",
        (
            RecordedEntity(PRIMARY, "vacuum", "primary", device_id="robot"),
            *entities,
        ),
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


def test_separate_device_remains_outside_mvp() -> None:
    descriptor = replace(entity("mop_drying", "switch", "roborock"), device_id="dock")
    ctx = context(descriptor)
    assert portable_entity(descriptor.entity_id, ctx) is None
    item = sample(**{descriptor.entity_id: "on"})
    assert resolve_activity(item, discover_signals([item], ctx)) == "docked"


def test_disabled_sleep_status_is_ignored() -> None:
    items = [sample(**{"sensor.state": "charging_completed", "sensor.status": "sleeping"})]
    signals = discover_signals(items, context(entity("state"), replace(entity("status"), disabled_by="user")))
    assert resolve_activity(items[0], signals) == "completed"
