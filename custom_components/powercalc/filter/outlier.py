from __future__ import annotations

from collections import deque
import statistics


class OutlierFilter:
    """Simple rolling-window outlier filter using median + MAD.

    - Warm-up: accepts the first `min_samples` values unconditionally.
    - After that: rejects values whose modified Z-score > `max_z_score`.
    """

    def __init__(
        self,
        window_size: int = 30,
        min_samples: int = 10,
        max_z_score: float = 5.0,
        max_expected_step: int = 1000,
    ) -> None:
        self._window_size = window_size
        self._min_samples = min_samples
        self._max_z_score = max_z_score
        self._values: deque[float] = deque(maxlen=window_size)
        self._max_expected_step = max_expected_step

    @property
    def values(self) -> list[float]:
        return list(self._values)

    def _is_outlier(self, value: float) -> bool:
        """Return True if value is considered an outlier."""
        if len(self._values) < self._min_samples:
            return False

        median = statistics.median(self._values)

        # 1) Always allow downward transitions (light turning OFF)
        if value <= median:
            return False

        # 2) Allow reasonable upward transitions (light turning ON)
        # e.g. below 200 W difference - always accept
        if value - median < self._max_expected_step:
            return False

        # 3) For larger jumps, use proper outlier detection (MAD)
        abs_devs = [abs(x - median) for x in self._values]
        mad = statistics.median(abs_devs) or 0

        if mad == 0:
            return False  # pragma: no cover

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
