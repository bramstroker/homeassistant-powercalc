"""Metadata mappings shared by vacuum recording suggestions and signal discovery.

Integration rules override common mappings, including explicit exclusions.
Define metadata, state meanings and source priorities here; the analyser applies
these rules to recorded values without integration-specific branches.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from measure.analyser.models import Activity
from measure.recording.models import RecordedEntity


class SignalPriority(IntEnum):
    ACTION_ENTITY = 0
    DEPRECATED_ACTION_ENTITY = 1
    ACTIVITY_FLAG = 2
    RELATED_STATE = 3
    RELATED_STATUS = 4
    VACUUM_STATE_ATTRIBUTE = 5
    STATUS_ATTRIBUTE = 6
    HA_STATE = 7


ATTRIBUTE_FLAGS = {"washing": Activity.WASHING, "drying": Activity.DRYING, "auto_empty_status": Activity.AUTO_EMPTYING}
STATUS_ATTRIBUTES = {
    "vacuum_state": SignalPriority.VACUUM_STATE_ATTRIBUTE,
    "status": SignalPriority.STATUS_ATTRIBUTE,
}


class EntitySignalType(StrEnum):
    IGNORE = "ignore"
    ACTION = "action"
    STATION = "station"
    STATUS = "status"
    CHARGING_STATUS = "charging_status"
    CHARGING_FLAG = "charging_flag"


@dataclass(frozen=True)
class EntitySignalRule:
    domains: tuple[str, ...]
    signal_type: EntitySignalType
    translation_key: str | None = None
    device_class: str | None = None
    activity: Activity | None = None
    priority: SignalPriority = SignalPriority.ACTION_ENTITY
    state_values: Mapping[Activity, frozenset[str]] | None = None
    inactive_states: frozenset[str] = frozenset()

    def matches(self, entity: RecordedEntity) -> bool:
        return (
            entity.domain in self.domains
            and (self.translation_key is None or entity.translation_key == self.translation_key)
            and (self.device_class is None or entity.device_class == self.device_class)
        )


# Preserve the existing vocabulary for legacy recordings and generic sources.
STATUS_VALUES: dict[Activity, frozenset[str]] = {
    Activity.AUTO_EMPTYING: frozenset(
        {"auto_emptying", "auto_empty", "emptying", "emptying_the_bin", "emptying_dustbin"}
    ),
    Activity.STATION_CLEANING: frozenset({"station_cleaning"}),
    Activity.WASHING: frozenset(
        {
            "washing",
            "mop_washing",
            "washing_mop",
            "washing_the_mop",
            "washing_the_mop_2",
            "clean_add_water",
            "adding_water",
        }
    ),
    Activity.DRYING: frozenset({"drying", "mop_drying", "drying_mop"}),
    Activity.CHARGING: frozenset({"charging"}),
    Activity.SLEEPING: frozenset({"sleeping", "sleep"}),
    Activity.COMPLETED: frozenset({"charging_completed", "charging_complete", "charging_done"}),
    Activity.DOCKED: frozenset({"docked"}),
    Activity.AWAY: frozenset(
        {
            "cleaning",
            "room_cleaning",
            "zone_cleaning",
            "spot_cleaning",
            "sweeping",
            "mopping",
            "sweeping_and_mopping",
            "returning",
            "returning_to_wash",
            "returning_auto_empty",
            "second_cleaning",
            "paused",
            "idle",
            "returning_to_washing",
            "building",
            "fast_mapping",
            "follow_wall_cleaning",
            "remote_control",
            "monitor_cruise",
            "monitor_spot",
            "summon_clean",
            "returning_home",
            "docking",
            "zoned_cleaning",
            "segment_cleaning",
            "going_to_wash_the_mop",
            "going_to_target",
            "mapping",
            "manual_mode",
            "remote_control_active",
            "patrol",
            "robot_status_mopping",
            "robot_status_clean_mop_cleaning",
            "robot_status_clean_mop_mopping",
            "robot_status_segment_mopping",
            "robot_status_segment_clean_mop_cleaning",
            "robot_status_segment_clean_mop_mopping",
            "robot_status_zoned_mopping",
            "robot_status_zoned_clean_mop_cleaning",
            "robot_status_zoned_clean_mop_mopping",
            "robot_status_back_to_dock_washing_duster",
        }
    ),
}

# State vocabularies are scoped to the source's role. In particular, station idle
# is not the same as vacuum idle, and dock cleaning need not mean robot cleaning.
STATION_VALUES = {
    activity: STATUS_VALUES[activity]
    for activity in [Activity.AUTO_EMPTYING, Activity.STATION_CLEANING, Activity.WASHING, Activity.DRYING]
}
CHARGING_VALUES = {
    Activity.CHARGING: frozenset({"charging"}),
    Activity.COMPLETED: frozenset({"charging_completed", "charging_complete", "charging_done"}),
}

# HA 2026.9.3 / python-roborock 7.4.2: V1 and Q10 share the status key.
# Keep their vocabulary separate from Q7, which exposes q7_status.
ROBOROCK_STATUS_VALUES = {
    **STATUS_VALUES,
    Activity.DOCKED: STATUS_VALUES[Activity.DOCKED] | {"waiting_to_charge"},
    Activity.AWAY: STATUS_VALUES[Activity.AWAY]
    | {
        "sweep_and_mop",
        "clean_mop_cleaning",
        "clean_mop_mopping",
        "segment_mopping",
        "segment_clean_mop_cleaning",
        "segment_clean_mop_mopping",
        "zoned_mopping",
        "zoned_clean_mop_cleaning",
        "zoned_clean_mop_mopping",
        "back_to_dock_washing_duster",
    },
}

ROBOROCK_Q7_VALUES = {
    Activity.WASHING: frozenset({"mop_cleaning"}),
    Activity.DRYING: frozenset({"mop_airdrying"}),
    Activity.CHARGING: frozenset({"charging"}),
    Activity.SLEEPING: frozenset({"sleeping"}),
    Activity.AWAY: frozenset({"waiting_for_orders", "paused", "docking", "sweep_moping", "sweep_moping_2", "moping"}),
}

COMMON_ENTITY_RULES = [
    EntitySignalRule(("binary_sensor", "switch"), EntitySignalType.ACTION, key, activity=activity)
    for key, activity in {
        "auto_emptying": Activity.AUTO_EMPTYING,
        "auto_empty": Activity.AUTO_EMPTYING,
        "washing": Activity.WASHING,
        "drying": Activity.DRYING,
        "mop_washing": Activity.WASHING,
        "mop_drying": Activity.DRYING,
        "mop_drying_status": Activity.DRYING,
        "dust_emptying": Activity.AUTO_EMPTYING,
    }.items()
]
COMMON_ENTITY_RULES.extend(
    [
        EntitySignalRule(
            ("sensor",),
            EntitySignalType.ACTION,
            "auto_empty_status",
            activity=Activity.AUTO_EMPTYING,
            state_values={Activity.AUTO_EMPTYING: frozenset({"active"})},
            inactive_states=frozenset({"idle", "not_performed"}),
        ),
        *[
            EntitySignalRule(
                ("sensor",),
                EntitySignalType.STATION,
                key,
                priority=SignalPriority.ACTIVITY_FLAG,
                state_values=STATION_VALUES,
                inactive_states=frozenset({"idle", "returning"}),
            )
            for key in ["station_state", "self_wash_base_status"]
        ],
        EntitySignalRule(("sensor",), EntitySignalType.STATUS, "state", priority=SignalPriority.RELATED_STATE),
        EntitySignalRule(("sensor",), EntitySignalType.STATUS, "status", priority=SignalPriority.RELATED_STATUS),
        EntitySignalRule(
            ("sensor",),
            EntitySignalType.CHARGING_STATUS,
            "charging_status",
            priority=SignalPriority.ACTIVITY_FLAG,
            state_values=CHARGING_VALUES,
            inactive_states=frozenset({"not_charging", "return_to_charge"}),
        ),
    ]
)

INTEGRATION_ENTITY_RULES: dict[str, list[EntitySignalRule]] = {
    "roborock": [
        EntitySignalRule(
            ("sensor",),
            EntitySignalType.STATUS,
            "status",
            priority=SignalPriority.RELATED_STATUS,
            state_values=ROBOROCK_STATUS_VALUES,
        ),
        EntitySignalRule(
            ("sensor",),
            EntitySignalType.STATUS,
            "q7_status",
            priority=SignalPriority.RELATED_STATUS,
            state_values=ROBOROCK_Q7_VALUES,
        ),
        # This binary sensor was deprecated in favour of the live mop_drying switch.
        EntitySignalRule(
            ("binary_sensor",),
            EntitySignalType.ACTION,
            "mop_drying_status",
            activity=Activity.DRYING,
            priority=SignalPriority.DEPRECATED_ACTION_ENTITY,
        ),
        # The charging flag remains on at completion; dust_collection enables auto-emptying.
        EntitySignalRule(("binary_sensor",), EntitySignalType.IGNORE, device_class="battery_charging"),
        EntitySignalRule(("switch",), EntitySignalType.IGNORE, "dust_collection"),
    ],
    "dreame_vacuum": [
        EntitySignalRule(
            ("binary_sensor",),
            EntitySignalType.CHARGING_FLAG,
            "charging_state",
            activity=Activity.CHARGING,
            priority=SignalPriority.ACTIVITY_FLAG,
        ),
        # Tasshack v1.0.11 / v2.0.0b25: paused is deliberately unresolved, not idle.
        EntitySignalRule(
            ("sensor",),
            EntitySignalType.STATION,
            "self_wash_base_status",
            priority=SignalPriority.ACTIVITY_FLAG,
            state_values={
                Activity.WASHING: frozenset({"washing", "clean_add_water", "adding_water"}),
                Activity.DRYING: frozenset({"drying"}),
            },
            inactive_states=frozenset({"idle", "returning"}),
        ),
        *[
            EntitySignalRule(("switch",), EntitySignalType.IGNORE, key)
            for key in ["auto_drying", "auto_dust_collecting", "self_clean"]
        ],
        EntitySignalRule(("sensor",), EntitySignalType.IGNORE, "hot_water_status"),
    ],
    "ecovacs": [
        # deebot-client 18.5.1; no station self-cleaning or completion state is exposed.
        EntitySignalRule(
            ("sensor",),
            EntitySignalType.STATION,
            "station_state",
            priority=SignalPriority.ACTIVITY_FLAG,
            state_values={
                Activity.AUTO_EMPTYING: frozenset({"emptying_dustbin"}),
                Activity.WASHING: frozenset({"washing_mop"}),
                Activity.DRYING: frozenset({"drying_mop"}),
            },
            inactive_states=frozenset({"idle"}),
        ),
        # Legacy py-sucks only. Modern devices expose no separate charging flag.
        EntitySignalRule(
            ("binary_sensor",),
            EntitySignalType.CHARGING_FLAG,
            device_class="battery_charging",
            activity=Activity.CHARGING,
            priority=SignalPriority.ACTIVITY_FLAG,
        ),
        EntitySignalRule(("select",), EntitySignalType.IGNORE, "auto_empty"),
    ],
}


def get_entity_signal_rule(entity: RecordedEntity) -> EntitySignalRule | None:
    for rule in [*INTEGRATION_ENTITY_RULES.get(entity.integration or "", []), *COMMON_ENTITY_RULES]:
        if rule.matches(entity):
            return None if rule.signal_type == EntitySignalType.IGNORE else rule
    return None
