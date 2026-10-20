"""Time post-charge idle power using a portable charging entity's state changes."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from measure.analyser.models import Activity, FeatureReference
from measure.analyser.vacuum.signals import ActivitySignal, find_charging_flag
from measure.recording.models import RecordingContext, RecordingSample

SETTLING_SECONDS = 30 * 60
IDLE_ACTIVITIES = {Activity.SLEEPING, Activity.COMPLETED, Activity.DOCKED}


@dataclass(frozen=True)
class PostChargeTiming:
    charging: ActivitySignal
    elapsed_seconds: Mapping[int, float]

    def get_elapsed(self, sample: RecordingSample) -> float | None:
        return self.elapsed_seconds.get(id(sample))


def build_post_charge_timing(samples: Sequence[RecordingSample], context: RecordingContext) -> PostChargeTiming | None:
    charging = find_charging_flag(samples, context)
    if charging is None:
        return None
    elapsed: dict[int, float] = {}
    previous: RecordingSample | None = None
    charge_end: float | None = None
    for sample in samples:
        if previous is None or sample.recording_id != previous.recording_id:
            charge_end = None
            previous = None
        matched = charging.matches(sample)
        if matched is not False:
            charge_end = None
        elif previous is not None:
            previous_value = charging.feature.get_value(previous)
            value = charging.feature.get_value(sample)
            if charging.matches(previous) is True:
                charge_end = sample.elapsed_seconds
            elif value != previous_value:
                # last_changed also resets between different inactive aliases.
                charge_end = None
        if charge_end is not None:
            elapsed[id(sample)] = sample.elapsed_seconds - charge_end
        previous = sample
    return PostChargeTiming(charging, elapsed)


@dataclass(frozen=True)
class SettlingBranch:
    activity: Activity
    settling_power: float
    standby_power: float
    timing: PostChargeTiming

    @property
    def complexity(self) -> int:
        return 2

    def estimate(self, sample: RecordingSample, battery: FeatureReference | None) -> float | None:
        elapsed = self.timing.get_elapsed(sample)
        if elapsed is None:
            return None
        return self.settling_power if elapsed < SETTLING_SECONDS else self.standby_power

    def build_power_template(self, context: RecordingContext) -> str:
        entity = self.timing.charging.resolve_entity(context)
        assert entity is not None
        # Use the State object: states(entity) returns a string without last_changed.
        return (
            f"{{{{ {self.settling_power} if "
            f"(now() - states[{entity!r}].last_changed).total_seconds() < {SETTLING_SECONDS} "
            f"else {self.standby_power} }}}}"
        )
