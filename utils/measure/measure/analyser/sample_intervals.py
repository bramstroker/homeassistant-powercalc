"""Time weights for trapezoidal integration over consecutive recording samples."""

from collections.abc import Sequence
from itertools import pairwise

from measure.recording.models import RecordingSample

MAX_SAMPLE_INTERVAL_SECONDS = 30


def calculate_sample_durations(
    samples: Sequence[RecordingSample], selected: Sequence[RecordingSample]
) -> dict[int, float]:
    """Give each endpoint half its interval's duration, keyed by sample identity.

    Use the original recording order so selecting an activity or training subset
    never bridges excluded samples, recording boundaries, or telemetry gaps.
    """
    selected_ids = {id(sample) for sample in selected}
    durations: dict[int, float] = {}
    for left, right in pairwise(samples):
        if id(left) not in selected_ids or id(right) not in selected_ids or left.recording_id != right.recording_id:
            continue
        delta = right.elapsed_seconds - left.elapsed_seconds
        if not 0 < delta <= MAX_SAMPLE_INTERVAL_SECONDS:
            continue
        for sample in (left, right):
            durations[id(sample)] = durations.get(id(sample), 0.0) + delta / 2
    return durations
