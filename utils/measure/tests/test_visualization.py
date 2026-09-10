import gzip
import json
from pathlib import Path
from unittest.mock import patch

from measure.request import MeasurementRequest, parse_measurement_request
from measure.visualization import (
    PlotDataError,
    PlotKind,
    build_plot_from_file,
    build_session_plots,
    model_has_linear_calibration,
)
import pytest


def light_request(*modes: str) -> MeasurementRequest:
    return parse_measurement_request(
        {
            "measure_type": "light",
            "model_id": "LCT010",
            "product_name": "Test light",
            "measure_device": "Test meter",
            "power_meter": {"type": "dummy"},
            "controller": {"type": "dummy"},
            "modes": list(modes),
        },
    )


def test_plots_work_before_model_id_is_known(tmp_path: Path) -> None:
    source = tmp_path / "brightness.csv"
    source.write_text("bri,watt\n1,0.5\n255,8.2\n", encoding="utf-8")
    result = build_session_plots(
        request=light_request("brightness").model_copy(update={"model_id": ""}),
        files={"measurement/brightness.csv": source},
    )
    assert result.plots[0].source == "measurement/brightness.csv"


def test_builds_all_light_plot_modes_from_plain_and_gzip_csv(tmp_path: Path) -> None:
    files = {
        "LCT010/brightness.csv": tmp_path / "brightness.csv",
        "LCT010/color_temp.csv.gz": tmp_path / "color_temp.csv.gz",
        "LCT010/hs.csv": tmp_path / "hs.csv",
        "LCT010/effect.csv": tmp_path / "effect.csv",
    }
    files["LCT010/brightness.csv"].write_text("bri,watt\n1,0.5\n255,8.2\n", encoding="utf-8")
    with gzip.open(files["LCT010/color_temp.csv.gz"], "wt", encoding="utf-8") as file:
        file.write("bri,mired,watt\n1,150,0.6\n255,500,8.5\n")
    files["LCT010/hs.csv"].write_text("bri,hue,sat,watt\n128,32768,255,4.2\n", encoding="utf-8")
    files["LCT010/effect.csv"].write_text(
        "effect,bri,watt\nColor loop,1,0.7\nColor loop,255,9.1\nPulse,128,5.0\n",
        encoding="utf-8",
    )

    result = build_session_plots(
        light_request("brightness", "color_temp", "hs", "effect"),
        files,
    )

    assert result.warnings == ()
    assert [plot.id for plot in result.plots] == ["brightness", "color_temp", "hs", "effect"]
    assert result.plots[0].kind is PlotKind.SCATTER
    assert result.plots[0].series[0].points[-1].y == pytest.approx(8.2)
    assert result.plots[1].series[0].points[0].color is not None
    assert result.plots[2].series[0].points[0].color is not None
    assert [series.label for series in result.plots[3].series] == ["Color loop", "Pulse"]


def test_prefers_plain_csv_when_compressed_copy_is_also_present(tmp_path: Path) -> None:
    plain = tmp_path / "brightness.csv"
    compressed = tmp_path / "brightness.csv.gz"
    plain.write_text("bri,watt\n1,1.0\n", encoding="utf-8")
    with gzip.open(compressed, "wt", encoding="utf-8") as file:
        file.write("bri,watt\n1,99.0\n")

    result = build_session_plots(
        light_request("brightness"),
        {
            "LCT010/brightness.csv.gz": compressed,
            "LCT010/brightness.csv": plain,
        },
    )

    assert result.plots[0].series[0].points[0].y == pytest.approx(1.0)
    assert result.plots[0].source == "LCT010/brightness.csv"


@pytest.mark.parametrize(
    "device_type, title, x_label",
    [
        ("smart_speaker", "Speaker calibration", "Volume (%)"),
        ("fan", "Fan calibration", "Fan speed (%)"),
        ("vacuum_robot", "Charging calibration", "Battery level (%)"),
        ("unknown", "Linear calibration", "Value"),
    ],
)
def test_builds_linear_model_plot_with_device_specific_labels(
    tmp_path: Path,
    device_type: str,
    title: str,
    x_label: str,
) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "device_type": device_type,
                "calculation_strategy": "linear",
                "linear_config": {"calibrate": ["100 -> 8.5", "0 -> 0.4", "50 -> 4.2"]},
            },
        ),
        encoding="utf-8",
    )

    plot = build_plot_from_file(model)

    assert plot.title == title
    assert plot.x_label == x_label
    assert [point.x for point in plot.series[0].points] == [0.0, 50.0, 100.0]


def test_builds_composite_model_plot_from_nested_linear_calibration(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "device_type": "vacuum_robot",
                "calculation_strategy": "composite",
                "composite_config": [
                    {"fixed": {"power": 648}},
                    {
                        "condition": {"condition": "state", "entity_id": "sensor.battery", "state": "on"},
                        "linear": {"calibrate": ["15 -> 17.31", "100 -> 8.14"]},
                    },
                    {"fixed": {"power": 2.6}},
                ],
            },
        ),
        encoding="utf-8",
    )

    plot = build_plot_from_file(model)

    assert plot.title == "Charging calibration"
    assert len(plot.series) == 1
    assert plot.series[0].label is None
    assert [(point.x, point.y) for point in plot.series[0].points] == [(15.0, 17.31), (100.0, 8.14)]


def test_builds_composite_model_plot_with_labelled_series(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "device_type": "fan",
                "calculation_strategy": "composite",
                "composite_config": {
                    "mode": "stop_at_first",
                    "strategies": [
                        {
                            "condition": {
                                "condition": "and",
                                "conditions": [
                                    {
                                        "condition": "state",
                                        "entity_id": "[[entity]]",
                                        "attribute": "oscillating",
                                        "state": True,
                                    },
                                    {
                                        "condition": "state",
                                        "entity_id": "[[entity_by_translation_key:direction]]",
                                        "state": "reverse",
                                    },
                                ],
                            },
                            "linear": {"calibrate": ["50 -> 8.06", "100 -> 28.48"]},
                        },
                        {"linear": {"calibrate": ["50 -> 6.25", "100 -> 27.36"]}},
                    ],
                },
            },
        ),
        encoding="utf-8",
    )

    plot = build_plot_from_file(model)

    assert plot.title == "Fan calibration"
    assert [series.label for series in plot.series] == [
        "oscillating = true AND direction = reverse",
        "Unconditional",
    ]
    assert plot.series[0].color != plot.series[1].color


def test_rejects_composite_model_without_linear_calibration(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "calculation_strategy": "composite",
                "composite_config": [{"fixed": {"power": 2.6}}],
            },
        ),
        encoding="utf-8",
    )

    with pytest.raises(PlotDataError, match="does not contain linear calibration data"):
        build_plot_from_file(model)


@pytest.mark.parametrize(
    "model_data",
    [
        None,
        {"calculation_strategy": "fixed"},
        {"calculation_strategy": "composite"},
        {"calculation_strategy": "composite", "composite_config": {}},
        {"calculation_strategy": "composite", "composite_config": [None, {"fixed": {"power": 1}}]},
    ],
)
def test_model_without_usable_linear_calibration_is_not_supported(model_data: object) -> None:
    assert model_has_linear_calibration(model_data) is False


def test_rejects_composite_model_without_valid_calibration_points(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "calculation_strategy": "composite",
                "composite_config": [{"linear": {"calibrate": [None, "invalid", "nan -> 1"]}}],
            },
        ),
        encoding="utf-8",
    )

    with pytest.raises(PlotDataError, match="no valid linear calibration entries found"):
        build_plot_from_file(model)


def test_composite_series_labels_handle_supported_condition_shapes(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    model.write_text(
        json.dumps(
            {
                "calculation_strategy": "composite",
                "composite_config": [
                    {
                        "condition": {
                            "condition": "not",
                            "conditions": [
                                {"condition": "state", "entity_id": ["switch.pump"], "state": ["on", "starting"]},
                            ],
                        },
                        "linear": {"calibrate": ["0 -> 1", "100 -> 2"]},
                    },
                    {
                        "condition": {"condition": "numeric_state", "entity_id": "sensor.speed", "above": 0},
                        "linear": {"calibrate": ["0 -> 2", "100 -> 3"]},
                    },
                    {
                        "condition": {"condition": "state", "entity_id": "[[entity]]", "state": "docked"},
                        "linear": {"calibrate": ["0 -> 3", "100 -> 4"]},
                    },
                    {
                        "condition": {"condition": "state", "state": "on"},
                        "linear": {"calibrate": ["0 -> 4", "100 -> 5"]},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    plot = build_plot_from_file(model)

    assert [series.label for series in plot.series] == [
        "NOT (switch.pump = on, starting)",
        "Strategy 2",
        "state = docked",
        "Strategy 4",
    ]


def test_builds_recorder_time_series_and_ignores_invalid_rows(tmp_path: Path) -> None:
    recording = tmp_path / "record.csv"
    recording.write_text("0.0,1.2\ninvalid,row\n2.0,3.4\n3.0,nan\n", encoding="utf-8")
    request = parse_measurement_request(
        {
            "measure_type": "recorder",
            "model_id": "measurement",
            "power_meter": {"type": "dummy"},
            "export_filename": "record.csv",
        },
    )

    result = build_session_plots(request, {"measurement/record.csv": recording})

    assert result.warnings == ()
    assert result.plots[0].kind is PlotKind.LINE
    assert result.plots[0].x_label == "Elapsed time (s)"
    assert [(point.x, point.y) for point in result.plots[0].series[0].points] == [(0.0, 1.2), (2.0, 3.4)]


def test_builds_complex_recorder_time_series_from_json_lines(tmp_path: Path) -> None:
    recording = tmp_path / "record.jsonl"
    recording.write_text(
        """{"record_type":"metadata","format_version":1,"primary_entity_id":"switch.plug","entities":[]}
{"record_type":"sample","elapsed_seconds":0.0,"power":1.2,"entities":{"switch.plug":{"state":"on","attributes":{}}}}
incomplete
{"elapsed_seconds":2.0,"power":3.4,"entities":{}}
{"elapsed_seconds":3.0,"power":"nan","entities":{}}
""",
        encoding="utf-8",
    )
    request = parse_measurement_request(
        {
            "measure_type": "recorder",
            "model_id": "measurement",
            "power_meter": {"type": "dummy"},
            "recorder_purpose": "complex_profile",
            "profile_recipe": "generic",
            "tracked_entity_ids": ["switch.plug"],
            "export_filename": "record.jsonl",
        },
    )

    result = build_session_plots(request, {"measurement/record.jsonl": recording})

    assert result.warnings == ()
    assert [(point.x, point.y) for point in result.plots[0].series[0].points] == [(0.0, 1.2), (2.0, 3.4)]


def test_downsamples_large_recorder_files_while_streaming(tmp_path: Path) -> None:
    recording = tmp_path / "record.csv"
    recording.write_text(
        "\n".join(f"{index},{999 if index == 10_000 else index % 20}" for index in range(20_000)),
        encoding="utf-8",
    )
    request = parse_measurement_request(
        {
            "measure_type": "recorder",
            "model_id": "measurement",
            "power_meter": {"type": "dummy"},
            "export_filename": "record.csv",
        },
    )

    with patch("measure.visualization.core._limit_line", side_effect=AssertionError("full input was materialized")):
        result = build_session_plots(
            request,
            {"measurement/record.csv": recording},
            max_line_points=8,
        )

    points = result.plots[0].series[0].points
    assert len(points) <= 8
    assert points[0].x == 0
    assert points[-1].x == 19_999
    assert max(point.y for point in points) == 999


def test_reports_invalid_artifact_without_hiding_other_plots(tmp_path: Path) -> None:
    brightness = tmp_path / "brightness.csv"
    color_temp = tmp_path / "color_temp.csv"
    brightness.write_text("bri,watt\n1,1.0\n", encoding="utf-8")
    color_temp.write_text("wrong,headers\n1,2\n", encoding="utf-8")

    result = build_session_plots(
        light_request("brightness", "color_temp"),
        {
            "LCT010/brightness.csv": brightness,
            "LCT010/color_temp.csv": color_temp,
        },
    )

    assert [plot.id for plot in result.plots] == ["brightness"]
    assert len(result.warnings) == 1
    assert "color_temp.csv" in result.warnings[0]


def test_reads_effect_csv_with_utf8_bom(tmp_path: Path) -> None:
    effect = tmp_path / "effect.csv.gz"
    with gzip.open(effect, "wt", encoding="utf-8-sig") as file:
        file.write("effect,bri,watt\nnone,5,3.85\nnone,15,4.72\n")

    plot = build_plot_from_file(effect)

    assert plot.id == "effect"
    assert [series.label for series in plot.series] == ["none"]


def test_limits_line_plot_points_without_losing_extrema(tmp_path: Path) -> None:
    recording = tmp_path / "record.csv"
    recording.write_text(
        "\n".join(f"{index},{100 if index == 50 else index % 7}" for index in range(100)),
        encoding="utf-8",
    )

    plot = build_plot_from_file(recording, max_points=20)

    assert len(plot.series[0].points) <= 20
    assert max(point.y for point in plot.series[0].points) == 100
