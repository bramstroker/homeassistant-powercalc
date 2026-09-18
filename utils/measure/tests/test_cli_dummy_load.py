from datetime import UTC, datetime
import json
from pathlib import Path

from measure.cli.const import QUESTION_DUMMY_LOAD
from measure.cli.dummy_load import (
    QUESTION_DUMMY_LOAD_DESCRIPTION,
    QUESTION_DUMMY_LOAD_MODE,
    CliDummyLoadCalibrationStore,
    apply_dummy_load_answers,
    dummy_load_questions,
)
from measure.cli.main import Measure
from measure.const import MeasureType
from measure.powermeter.spec import HassPowerMeterSpec
from measure.request import (
    AverageMeasurementRequest,
    DummyLoadCalibrationRequest,
    DummyLoadReuseRequest,
)
import pytest

from tests.conftest import MockConfigFactory


def _request(entity_id: str = "sensor.plug_power") -> AverageMeasurementRequest:
    return AverageMeasurementRequest(
        power_meter=HassPowerMeterSpec(
            entity_id=entity_id,
            voltage_entity_id="sensor.plug_voltage",
        ),
    )


def test_store_saves_and_loads_calibration_for_matching_power_meter(tmp_path: Path) -> None:
    store = CliDummyLoadCalibrationStore(tmp_path)
    request = _request().model_copy(
        update={"dummy_load": DummyLoadCalibrationRequest(description="40 W incandescent bulb")},
    )

    calibration = store.save(request, 1_322.4)

    assert calibration.description == "40 W incandescent bulb"
    assert calibration.resistance == pytest.approx(1_322.4)
    assert datetime.fromisoformat(calibration.calibrated_at).tzinfo == UTC
    assert store.load(request) is None
    assert store.load(_request()) == calibration
    assert store.load(_request("sensor.other_power")) is None


def test_store_upgrades_legacy_scalar_for_current_power_meter(tmp_path: Path) -> None:
    legacy_path = tmp_path / "dummy_load_resistance"
    legacy_path.write_text("1322.4", encoding="utf-8")
    store = CliDummyLoadCalibrationStore(tmp_path)

    calibration = store.load(_request())

    assert calibration is not None
    assert calibration.description == "Legacy resistive dummy load"
    assert calibration.resistance == pytest.approx(1_322.4)
    assert not legacy_path.exists()
    stored = json.loads((tmp_path / "dummy_load_calibration.json").read_text(encoding="utf-8"))
    assert stored["power_meter_fingerprint"] == calibration.power_meter_fingerprint


@pytest.mark.parametrize("contents", ["not json", "[]", '{"resistance": -1}'])
def test_store_ignores_corrupt_calibration(tmp_path: Path, caplog: pytest.LogCaptureFixture, contents: str) -> None:
    path = tmp_path / "dummy_load_calibration.json"
    path.write_text(contents, encoding="utf-8")

    assert CliDummyLoadCalibrationStore(tmp_path).load(_request()) is None
    assert "Ignoring invalid CLI dummy-load calibration" in caplog.text
    assert path.read_text(encoding="utf-8") == contents


def test_corrupt_calibration_falls_back_to_valid_legacy_resistance(tmp_path: Path) -> None:
    (tmp_path / "dummy_load_calibration.json").write_text("not json", encoding="utf-8")
    legacy_path = tmp_path / "dummy_load_resistance"
    legacy_path.write_text("1000", encoding="utf-8")
    store = CliDummyLoadCalibrationStore(tmp_path)

    calibration = store.load(_request())

    assert calibration is not None
    assert calibration.resistance == 1000
    assert store.load(_request()) == calibration
    assert not legacy_path.exists()


@pytest.mark.parametrize("contents", ["not a number", "0", "-100"])
def test_store_ignores_invalid_legacy_resistance(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, contents: str
) -> None:
    path = tmp_path / "dummy_load_resistance"
    path.write_text(contents, encoding="utf-8")

    assert CliDummyLoadCalibrationStore(tmp_path).load(_request()) is None
    assert "Ignoring invalid legacy dummy-load resistance" in caplog.text
    assert path.read_text(encoding="utf-8") == contents
    assert not (tmp_path / "dummy_load_calibration.json").exists()


def test_store_requires_dummy_load_configuration_before_saving(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="without dummy-load configuration"):
        CliDummyLoadCalibrationStore(tmp_path).save(_request(), 1000)

    assert list(tmp_path.iterdir()) == []


def test_reuse_requires_available_matching_calibration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no longer available for this power meter"):
        apply_dummy_load_answers(
            _request(),
            {QUESTION_DUMMY_LOAD: True, QUESTION_DUMMY_LOAD_MODE: "reuse"},
            CliDummyLoadCalibrationStore(tmp_path),
        )


def test_disabled_dummy_load_questions_do_not_load_calibration(
    tmp_path: Path, mock_config_factory: MockConfigFactory
) -> None:
    questions = dummy_load_questions(MeasureType.AVERAGE, mock_config_factory(), CliDummyLoadCalibrationStore(tmp_path))
    mode_question = next(question for question in questions if question.name == QUESTION_DUMMY_LOAD_MODE)
    mode_question.answers = {QUESTION_DUMMY_LOAD: False}

    assert mode_question.choices == [("Calibrate the connected dummy load", "calibrate")]


def test_dummy_load_questions_offer_reuse_for_matching_calibration(
    tmp_path: Path,
    mock_config_factory: MockConfigFactory,
) -> None:
    environment = mock_config_factory({"selected_power_meter": "hass"})
    store = CliDummyLoadCalibrationStore(tmp_path)
    calibration_request = _request().model_copy(
        update={"dummy_load": DummyLoadCalibrationRequest(description="Ceramic heater")},
    )
    store.save(calibration_request, 1_000)
    questions = dummy_load_questions(MeasureType.AVERAGE, environment, store)
    mode_question = next(question for question in questions if question.name == QUESTION_DUMMY_LOAD_MODE)
    mode_question.answers = {
        QUESTION_DUMMY_LOAD: True,
        "powermeter_entity_id": "sensor.plug_power",
        "voltagemeter_entity_id": "sensor.plug_voltage",
        "duration": 60,
    }

    assert mode_question.choices == [
        ("Use saved calibration: Ceramic heater (1000.00 Ω)", "reuse"),
        ("Calibrate the connected dummy load", "calibrate"),
    ]


def test_apply_dummy_load_answers_builds_calibration_request(tmp_path: Path) -> None:
    request = apply_dummy_load_answers(
        _request(),
        {
            QUESTION_DUMMY_LOAD: True,
            QUESTION_DUMMY_LOAD_MODE: "calibrate",
            QUESTION_DUMMY_LOAD_DESCRIPTION: "Ceramic heater",
        },
        CliDummyLoadCalibrationStore(tmp_path),
    )

    assert request.dummy_load == DummyLoadCalibrationRequest(description="Ceramic heater")


def test_apply_dummy_load_answers_builds_reuse_request(tmp_path: Path) -> None:
    store = CliDummyLoadCalibrationStore(tmp_path)
    request = _request().model_copy(
        update={"dummy_load": DummyLoadCalibrationRequest(description="Ceramic heater")},
    )
    store.save(request, 1_000)

    reused = apply_dummy_load_answers(
        _request(),
        {
            QUESTION_DUMMY_LOAD: True,
            QUESTION_DUMMY_LOAD_MODE: "reuse",
        },
        store,
    )

    assert reused.dummy_load == DummyLoadReuseRequest(
        description="Ceramic heater",
        resistance=1_000,
    )


def test_apply_dummy_load_answers_leaves_request_unchanged_when_disabled(tmp_path: Path) -> None:
    request = _request()

    assert (
        apply_dummy_load_answers(
            request,
            {QUESTION_DUMMY_LOAD: False},
            CliDummyLoadCalibrationStore(tmp_path),
        )
        is request
    )


@pytest.mark.parametrize("measure_type", list(MeasureType))
def test_every_cli_measurement_type_offers_dummy_load(
    tmp_path: Path,
    mock_config_factory: MockConfigFactory,
    measure_type: MeasureType,
) -> None:
    measure = Measure(
        mock_config_factory({"selected_power_meter": "hass"}),
        dummy_load_calibration_store=CliDummyLoadCalibrationStore(tmp_path),
    )
    measure.measure_type = measure_type

    names = [question.name for question in measure.get_questions([])]

    assert names.count(QUESTION_DUMMY_LOAD) == 1
    assert QUESTION_DUMMY_LOAD_MODE in names
    assert QUESTION_DUMMY_LOAD_DESCRIPTION in names
