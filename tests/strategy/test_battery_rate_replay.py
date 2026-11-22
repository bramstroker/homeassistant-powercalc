from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from homeassistant.core import HomeAssistant
import pytest

from utils import replay_battery_rate
from utils.replay_battery_rate import ChargeWindow, Replay, Trace, read_trace, report

TRACE = """timestamp_local,battery_pct,status,mop_drying,plug_energy_kwh
2026-10-24T00:00:00,95,charging,off,0
2026-10-24T00:05:00,100,charging,off,0.005
2026-10-24T00:10:00,100,charging,on,0.010
2026-10-24T00:10:05,100,charging,on,0.011
2026-10-24T00:15:00,100,cleaning,off,0.015
2026-10-24T00:20:00,95,cleaning,off,0.016
2026-10-24T00:25:00,95,charging,off,0.017
"""
START = datetime(2026, 10, 24)


def test_replay_uses_events_and_holds_power_between_updates(hass: HomeAssistant) -> None:
    replay = Replay(Trace(TRACE), START, START + timedelta(minutes=30), 10, hass)
    assert replay.energy(START, START + timedelta(minutes=5)) == pytest.approx(3.5 / 12)
    assert replay.energy(START + timedelta(minutes=5), START + timedelta(minutes=10)) == pytest.approx(32.3 / 12)
    assert replay.energy(START, START + timedelta(minutes=30), charging_only=True) == pytest.approx(4.8)
    assert replay.energy(START, START + timedelta(minutes=30), cut_at_full=True) == pytest.approx(3.5 / 2 + 57.2 / 12)
    assert all(point.timestamp != START + timedelta(minutes=10, seconds=5) for point in replay.points)
    assert replay.trace.interpolate_energy(START + timedelta(minutes=2, seconds=30)) == 2.5
    assert replay.trace.interpolate_energy(START + timedelta(minutes=31)) == 17
    errors = replay.power_errors()
    assert "First 15 min" in errors
    assert "100% +/-15 min" in errors


def test_replay_measures_steady_power_spans(hass: HomeAssistant) -> None:
    trace = Trace(TRACE.replace(",100,", ",96,"))
    replay = Replay(trace, START, START + timedelta(minutes=30), 10, hass)
    assert "Steady" in replay.power_errors()


def test_replay_reads_same_trace_from_directory_and_zip(tmp_path: Path) -> None:
    filename = "jarvis_charge_example.csv"
    (tmp_path / filename).write_text(TRACE)
    archive = tmp_path / "bundle.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr(filename, TRACE)
    assert read_trace(tmp_path, "example").readings == read_trace(archive, "example").readings


def test_report_aggregates_departures_only_after_fifteen_minutes(
    hass: HomeAssistant, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "jarvis_charge_already_full.csv").write_text(TRACE, encoding="utf-8")
    rising_trace = """timestamp_local,battery_pct,status,mop_drying,plug_energy_kwh
2026-10-24T00:00:00,20,charging,off,0
2026-10-24T00:20:00,30,charging,off,0.004
2026-10-24T00:25:00,50,charging,off,0.009
2026-10-24T00:30:00,70,charging,off,0.014
2026-10-24T00:35:00,90,charging,off,0.019
2026-10-24T00:40:00,100,charging,off,0.024
"""
    (tmp_path / "jarvis_charge_rising.csv").write_text(rising_trace, encoding="utf-8")
    start, end = START.isoformat(), (START + timedelta(minutes=40)).isoformat()
    monkeypatch.setattr(
        replay_battery_rate,
        "WINDOWS",
        [
            ChargeWindow("Already full", "already_full", start, end, True),
            ChargeWindow("Rising", "rising", start, end, False),
        ],
    )

    report(tmp_path, 10, hass)

    output = capsys.readouterr().out
    assert "| 30% | 4.00 |" in output
    assert "| 50% | 9.00 |" in output
    assert "| 70% | 14.00 |" in output
    assert "| 90% | 19.00 |" in output
