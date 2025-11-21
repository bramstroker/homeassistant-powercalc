from __future__ import annotations

from collections import deque
import statistics
from typing import Deque, Iterable


class OutlierFilter:
    """Simple rolling-window outlier filter using median + MAD.

    - Warm-up: accepts the first `min_samples` values unconditionally.
    - After that: rejects values whose modified Z-score > `max_z_score`.
    """

    def __init__(
        self,
        window_size: int = 30,
        min_samples: int = 5,
        max_z_score: float = 3.5,
    ) -> None:
        self._window_size = window_size
        self._min_samples = min_samples
        self._max_z_score = max_z_score
        self._values: Deque[float] = deque(maxlen=window_size)

    @property
    def values(self) -> Iterable[float]:
        return tuple(self._values)

    def _is_outlier(self, value: float) -> bool:
        """Return True if value is considered an outlier."""
        if len(self._values) < self._min_samples:
            return False

        median = statistics.median(self._values)
        abs_devs = [abs(x - median) for x in self._values]
        mad = statistics.median(abs_devs)

        if mad == 0:
            # All recent values are (almost) identical → treat everything as inlier
            return False

        # Modified Z-score
        z = 0.6745 * (value - median) / mad
        return abs(z) > self._max_z_score

    def accept(self, value: float) -> bool:
        """Return True if value should be accepted (not an outlier).

        Also updates the internal window if the value is accepted.
        """
        if self._is_outlier(value):
            return False

        self._values.append(value)
        return True