# ruff: noqa: T201
"""Replay issue #5090's CSV bundle against the production battery-rate strategy.

Run from the repository root:
    uv run python -m utils.replay_battery_rate /tmp/replay_jarvis_bundle_v2.zip

The archive is input data only. No code from the downloaded bundle is executed.
"""

import argparse
import asyncio
from bisect import bisect_right
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import io
from pathlib import Path
from zipfile import ZipFile

from homeassistant.core import HomeAssistant

from custom_components.powercalc.strategy.battery_rate import BatteryRateStrategy

BASE = Decimal("3.5")
DRYING = Decimal("57.2")
COEFFICIENT = Decimal("0.96")


@dataclass
class Reading:
    timestamp: datetime
    battery: Decimal
    charging: bool
    drying: bool
    energy: float


@dataclass
class ChargeWindow:
    label: str
    filename: str
    start: str
    end: str
    calibration: bool


WINDOWS = [
    ChargeWindow("Tue 20", "2026-10-20_tue", "2026-10-20T10:00:21", "2026-10-20T12:35:00", True),
    ChargeWindow("Wed 21", "2026-10-21_wed", "2026-10-21T10:26:03", "2026-10-21T14:35:00", True),
    ChargeWindow("Thu 22", "2026-10-22_thu", "2026-10-22T10:20:01", "2026-10-22T13:30:00", True),
    ChargeWindow("Fri 23", "2026-10-23_fri", "2026-10-23T10:24:02", "2026-10-23T13:00:00", True),
    ChargeWindow("Sat 24", "2026-10-24_sat", "2026-10-24T21:30:58", "2026-10-25T01:50:00", False),
    ChargeWindow("Mon 26 recharge", "2026-10-26_mon", "2026-10-26T10:26:00", "2026-10-26T11:26:14", False),
    ChargeWindow("Mon 26 final", "2026-10-26_mon", "2026-10-26T11:43:25", "2026-10-26T13:58:00", False),
]


class Trace:
    def __init__(self, text: str) -> None:
        self.readings = [
            Reading(
                timestamp=datetime.fromisoformat(row["timestamp_local"]),
                battery=Decimal(row["battery_pct"]),
                charging=row["status"] in {"charging", "docked"},
                drying=row["mop_drying"] == "on",
                energy=float(row["plug_energy_kwh"]) * 1000,
            )
            for row in csv.DictReader(io.StringIO(text))
        ]
        self.timestamps = [reading.timestamp for reading in self.readings]
        self.ticks: list[Reading] = []
        for reading in self.readings:
            if not self.ticks or reading.energy != self.ticks[-1].energy:
                self.ticks.append(reading)

    def at(self, now: datetime) -> Reading:
        return self.readings[max(0, bisect_right(self.timestamps, now) - 1)]

    def interpolate_energy(self, now: datetime) -> float:
        for left, right in zip(self.ticks, self.ticks[1:], strict=False):
            if left.timestamp <= now <= right.timestamp:
                fraction = (now - left.timestamp) / (right.timestamp - left.timestamp)
                return left.energy + fraction * (right.energy - left.energy)
        return self.at(now).energy


@dataclass
class PowerPoint:
    timestamp: datetime
    total: float
    charging: float


class Replay:
    def __init__(self, trace: Trace, start: datetime, end: datetime, window_minutes: int, hass: HomeAssistant) -> None:
        self.trace = trace
        self.start = start
        self.end = end
        strategy = BatteryRateStrategy(
            hass,
            {
                "entity_id": "sensor.battery",
                "energy_per_percent": COEFFICIENT,
                "base_power": BASE,
                "window": window_minutes * 60,
            },
        )
        events = {start, end}
        timer = start + timedelta(seconds=60)
        while timer < end:
            events.add(timer)
            timer += timedelta(seconds=60)
        previous = trace.at(start)
        for reading in trace.readings:
            if not start < reading.timestamp < end:
                continue
            if (reading.battery, reading.charging, reading.drying) != (
                previous.battery,
                previous.charging,
                previous.drying,
            ):
                events.add(reading.timestamp)
            previous = reading
        self.points: list[PowerPoint] = []
        for timestamp in sorted(events):
            reading = trace.at(timestamp)
            strategy.record_reading(timestamp, reading.battery)
            power = strategy.calculate_power(timestamp)
            assert power is not None
            charging = float(power - BASE) if reading.charging else 0
            base = float(BASE + (DRYING if reading.drying else 0))
            self.points.append(PowerPoint(timestamp, base + charging, charging))

    def energy(
        self, start: datetime, end: datetime, *, charging_only: bool = False, cut_at_full: bool = False
    ) -> float:
        total = 0.0
        for point, following in zip(self.points, self.points[1:], strict=False):
            left, right = max(start, point.timestamp), min(end, following.timestamp)
            if left >= right:
                continue
            power = point.charging if charging_only else point.total
            if cut_at_full and self.trace.at(point.timestamp).battery >= 100:
                power -= point.charging
            total += power * (right - left).total_seconds() / 3600
        return total

    def power_errors(self) -> dict[str, list[float]]:
        ticks = [tick for tick in self.trace.ticks if self.start <= tick.timestamp <= self.end][1:]
        full = next(
            (r.timestamp for r in self.trace.readings if self.start <= r.timestamp < self.end and r.battery >= 100),
            None,
        )
        errors: dict[str, list[float]] = {}
        index = 0
        while index < len(ticks) - 1:
            following = index + 1
            while following < len(ticks) - 1 and ticks[following].timestamp - ticks[index].timestamp < timedelta(
                minutes=5
            ):
                following += 1
            left, right = ticks[index], ticks[following]
            elapsed = (right.timestamp - left.timestamp).total_seconds()
            if elapsed < 300:
                break
            plug = (right.energy - left.energy) * 3600 / elapsed
            model = self.energy(left.timestamp, right.timestamp) * 3600 / elapsed
            middle = left.timestamp + (right.timestamp - left.timestamp) / 2
            if middle < self.start + timedelta(minutes=15):
                segment = "First 15 min"
            elif full is not None and abs(middle - full) <= timedelta(minutes=15):
                segment = "100% +/-15 min"
            else:
                segment = "Steady"
            errors.setdefault(segment, []).append(model - plug)
            index = following
        return errors


def read_trace(source: Path, filename: str) -> Trace:
    name = f"jarvis_charge_{filename}.csv"
    if source.is_dir():
        return Trace((source / name).read_text())
    with ZipFile(source) as archive:
        return Trace(archive.read(name).decode())


@dataclass
class EnergyTotals:
    plug: float = 0.0
    model: float = 0.0
    pending: float = 0.0


def report(source: Path, window_minutes: int, hass: HomeAssistant) -> None:
    print(f"\n## Window: {window_minutes} minutes\n")
    print("| Charge | Set | Plug Wh | Native Wh | Error | Cut at 100% Wh |")
    print("|---|---|---:|---:|---:|---:|")
    plug_total = model_total = holdout_plug = holdout_model = 0.0
    segments: dict[str, list[float]] = {}
    departures = {level: EnergyTotals() for level in [30, 50, 70, 90]}
    for window in WINDOWS:
        trace = read_trace(source, window.filename)
        start, end = datetime.fromisoformat(window.start), datetime.fromisoformat(window.end)
        replay = Replay(trace, start, end, window_minutes, hass)
        plug = trace.at(end).energy - trace.at(start).energy
        model = replay.energy(start, end)
        cut = replay.energy(start, end, cut_at_full=True)
        print(
            f"| {window.label} | {'Calibration' if window.calibration else 'Holdout'} | {plug:.1f} | "
            f"{model:.2f} | {model / plug - 1:+.2%} | {cut:.2f} |"
        )
        plug_total += plug
        model_total += model
        if not window.calibration:
            holdout_plug += plug
            holdout_model += model
        if start < datetime(2026, 10, 22):
            continue  # The first two traces have only 10 Wh counter resolution.
        for segment, errors in replay.power_errors().items():
            segments.setdefault(segment, []).extend(errors)
        for level, aggregate in departures.items():
            departure = next(
                (r.timestamp for r in trace.readings if start <= r.timestamp < end and r.battery >= level), None
            )
            if departure is None or departure - start < timedelta(minutes=15):
                continue
            departure_plug = trace.interpolate_energy(departure) - trace.interpolate_energy(start)
            departure_model = replay.energy(start, departure)
            gained = trace.at(departure).battery - trace.at(start).battery
            pending = float(gained * COEFFICIENT) - replay.energy(start, departure, charging_only=True)
            aggregate.plug += departure_plug
            aggregate.model += departure_model
            aggregate.pending += max(0, pending)
    print(f"| **Total** | | {plug_total:.1f} | {model_total:.2f} | {model_total / plug_total - 1:+.2%} | |")
    print(f"\nHoldout: {holdout_model:.2f} / {holdout_plug:.1f} Wh ({holdout_model / holdout_plug - 1:+.2%}).\n")
    print("| Power segment | Counter spans >=5 min | MAE W | Bias W |")
    print("|---|---:|---:|---:|")
    for segment, errors in segments.items():
        print(
            f"| {segment} | {len(errors)} | {sum(abs(e) for e in errors) / len(errors):.2f} | "
            f"{sum(errors) / len(errors):+.2f} |"
        )
    print("\nHypothetical departures (aggregated Oct 22 onward; counter interpolated between ticks):\n")
    print("| Departure at | Plug Wh | Native Wh before departure | Error | Uncounted charging Wh |")
    print("|---|---:|---:|---:|---:|")
    for level, aggregate in departures.items():
        print(
            f"| {level}% | {aggregate.plug:.2f} | {aggregate.model:.2f} | "
            f"{aggregate.model / aggregate.plug - 1:+.2%} | {aggregate.pending:.2f} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Issue #5090 v2 ZIP bundle or directory containing its CSVs")
    args = parser.parse_args()
    print("# Battery-rate native replay\n")
    print("Fixed coefficient: 0.96 Wh/%, baseline: 3.5 W, drying: +57.2 W. No power clamp or energy compensation.")
    print(
        "Fresh window at each charge start. Battery/status/drying events and a 60 s timer update power; "
        "integration holds power between events."
    )
    print("The first four charges are calibration data; the last three are holdout data. No coefficient is refitted.")
    asyncio.run(async_replay(args.source))


async def async_replay(source: Path) -> None:
    hass = HomeAssistant(str(source.parent))
    try:
        for window_minutes in [5, 10, 20]:
            report(source, window_minutes, hass)
    finally:
        await hass.async_stop(force=True)


if __name__ == "__main__":
    main()
