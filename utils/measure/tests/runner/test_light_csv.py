import csv
import gzip
from pathlib import Path

from measure.controller.light.const import LutMode
from measure.runner.light.csv import (
    compress_light_csv,
    has_measurement_rows,
    inspect_light_csv,
    open_csv_writer,
    repair_incomplete_csv_tail,
)
from measure.runner.light.plan import ColorTempVariation, EffectVariation, HsVariation, Variation
from measure.tuning import MeasurementParameters
import pytest


@pytest.mark.parametrize(
    "tail,discarded_rows",
    [("", 0), ("255,", 1), ("255,8.2", 1), ("255,\nbroken\n", 2), ("255,nan\n", 1), ("255,1,extra\n", 1)],
)
def test_inspection_is_read_only_and_repair_preserves_complete_measurements(
    tmp_path: Path, tail: str, discarded_rows: int
) -> None:
    path = tmp_path / "brightness.csv"
    complete = "bri,watt\n1,0.45\n128,4.20\n"
    path.write_text(complete + tail)
    original = path.read_bytes()

    inspection = inspect_light_csv(path, LutMode.BRIGHTNESS)

    assert path.read_bytes() == original
    assert inspection.last_complete_variation == Variation(128)
    assert inspection.incomplete_tail_rows == discarded_rows

    repair_incomplete_csv_tail(path, inspection)

    assert path.read_text() == complete
    if not discarded_rows:
        assert path.read_bytes() == original
    assert inspect_light_csv(path, LutMode.BRIGHTNESS).incomplete_tail_rows == 0


@pytest.mark.parametrize("contents", ["", "bri,watt\n", "bri,watt\n1,", "bri,watt\n1,1.0", "bri,watt\n1,\n"])
def test_recordings_without_a_complete_measurement_have_no_resume_point(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "brightness.csv"
    path.write_text(contents)

    inspection = inspect_light_csv(path, LutMode.BRIGHTNESS)

    assert inspection.last_complete_variation is None
    assert path.read_text() == contents


@pytest.mark.parametrize(
    "mode,contents,expected",
    [
        (LutMode.BRIGHTNESS, "bri,watt\r\n1,0.5\r\n", Variation(1)),
        (LutMode.COLOR_TEMP, "bri,mired,watt\n128,300,4.2\n", ColorTempVariation(128, 300)),
        (LutMode.HS, "bri,hue,sat,watt\n128,1000,200,4.2\n", HsVariation(128, 1000, 200)),
        (LutMode.EFFECT, 'effect,bri,watt\n"Night, sky",128,4.2\n', EffectVariation(128, "Night, sky")),
        (LutMode.EFFECT, 'effect,bri,watt\n"Night\nsky",128,4.2\n', EffectVariation(128, "Night\nsky")),
    ],
)
def test_inspection_supports_each_light_mode(tmp_path: Path, mode: LutMode, contents: str, expected: Variation) -> None:
    path = tmp_path / "measurement.csv"
    path.write_bytes(contents.encode())

    assert inspect_light_csv(path, mode).last_complete_variation == expected


@pytest.mark.parametrize(
    "contents", ["wrong,watt\n1,1.0\n", "bri,watt,time\n1,1.0,20260918090000\n", 'bri,watt\n1,"2\n']
)
def test_invalid_csv_is_rejected_without_changes(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "brightness.csv"
    path.write_text(contents)

    with pytest.raises(ValueError, match=r"(?:header does not match|Invalid measurement CSV)"):
        inspect_light_csv(path, LutMode.BRIGHTNESS)

    assert path.read_text() == contents


def test_datetime_column_is_checked_against_configuration(tmp_path: Path) -> None:
    path = tmp_path / "brightness.csv"
    path.write_text("bri,watt,time\n1,0.45,20260918090000\n128,4.2\n")

    inspection = inspect_light_csv(path, LutMode.BRIGHTNESS, include_datetime=True)

    assert inspection.last_complete_variation == Variation(1)
    assert inspection.incomplete_tail_rows == 1


@pytest.mark.parametrize("include_datetime", [False, True])
@pytest.mark.parametrize(
    "variation", [Variation(1), ColorTempVariation(1, 300), HsVariation(1, 1000, 200), EffectVariation(1, "Night, sky")]
)
def test_writer_output_can_be_inspected_and_appended(
    tmp_path: Path, include_datetime: bool, variation: Variation
) -> None:
    path = tmp_path / "measurement.csv"
    parameters = MeasurementParameters(csv_add_datetime_column=include_datetime)
    with open_csv_writer(path, variation.mode, append=False, parameters=parameters) as writer:
        writer.write_measurement(variation, 4.2)
    with open_csv_writer(path, variation.mode, append=True, parameters=parameters) as writer:
        writer.write_measurement(variation, 4.3)

    inspection = inspect_light_csv(path, variation.mode, include_datetime=include_datetime)

    assert inspection.last_complete_variation == variation
    assert inspection.incomplete_tail_rows == 0
    with path.open(newline="") as file:
        rows = list(csv.reader(file))
    assert len(rows) == 3
    if include_datetime:
        assert rows[0][-1] == "time"
        assert all(row[-1].isdigit() and len(row[-1]) == 14 for row in rows[1:])


@pytest.mark.parametrize(
    "contents,expected", [(None, False), ("", False), ("bri,watt\n", False), ("bri,watt\n1,", True)]
)
def test_has_measurement_rows(tmp_path: Path, contents: str | None, expected: bool) -> None:
    path = tmp_path / "brightness.csv"
    if contents is not None:
        path.write_text(contents)

    assert has_measurement_rows(path) is expected


def test_compression_keeps_original_csv_and_preserves_its_contents(tmp_path: Path) -> None:
    path = tmp_path / "brightness.csv"
    contents = b"bri,watt\r\n1,1.25\r\n"
    path.write_bytes(contents)

    compress_light_csv(path)

    assert path.read_bytes() == contents
    assert gzip.decompress((tmp_path / "brightness.csv.gz").read_bytes()) == contents


def test_effect_without_a_name_is_not_a_complete_measurement(tmp_path: Path) -> None:
    path = tmp_path / "effect.csv"
    path.write_text("effect,bri,watt\n,128,4.2\n")

    inspection = inspect_light_csv(path, LutMode.EFFECT)

    assert inspection.last_complete_variation is None
    assert inspection.incomplete_tail_rows == 1
