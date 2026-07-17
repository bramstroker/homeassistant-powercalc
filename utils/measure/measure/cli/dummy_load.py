from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any

import inquirer
from inquirer.questions import Question

from measure.cli.environment import CliEnvironment
from measure.cli.request_adapter import request_from_answers
from measure.const import PROJECT_DIR, QUESTION_DUMMY_LOAD, MeasureType
from measure.dummy_load import DummyLoadCalibration, power_meter_fingerprint
from measure.request import (
    BaseMeasurementRequest,
    DummyLoadCalibrationRequest,
    DummyLoadReuseRequest,
    MeasurementRequest,
    parse_measurement_request,
)

QUESTION_DUMMY_LOAD_MODE = "dummy_load_mode"
QUESTION_DUMMY_LOAD_DESCRIPTION = "dummy_load_description"

_CALIBRATION_FILENAME = "dummy_load_calibration.json"
_LEGACY_FILENAME = "dummy_load_resistance"
_LEGACY_DESCRIPTION = "Legacy resistive dummy load"
_LOGGER = logging.getLogger(__name__)


class CliDummyLoadCalibrationStore:
    """Persist one CLI dummy-load calibration and bind it to its power meter."""

    def __init__(self, persistent_directory: Path | None = None) -> None:
        self._persistent_directory = persistent_directory or PROJECT_DIR / ".persistent"

    def load(self, request: BaseMeasurementRequest) -> DummyLoadCalibration | None:
        """Load a calibration compatible with the request's power meter."""

        if isinstance(request.dummy_load, DummyLoadCalibrationRequest):
            return None
        calibration = self._load_json()
        if calibration is None:
            calibration = self._upgrade_legacy(request)
        if calibration is None or calibration.power_meter_fingerprint != power_meter_fingerprint(request.power_meter):
            return None
        return calibration

    def save(self, request: BaseMeasurementRequest, resistance: float) -> DummyLoadCalibration:
        """Store a successfully measured resistance for later CLI sessions."""

        if request.dummy_load is None:
            raise ValueError("Cannot save a dummy-load calibration for a request without dummy-load configuration")
        calibration = DummyLoadCalibration(
            description=request.dummy_load.description,
            resistance=resistance,
            calibrated_at=datetime.now(UTC).isoformat(),
            power_meter_fingerprint=power_meter_fingerprint(request.power_meter),
        )
        self._write(calibration)
        return calibration

    def _load_json(self) -> DummyLoadCalibration | None:
        path = self._persistent_directory / _CALIBRATION_FILENAME
        if not path.exists():
            return None
        try:
            return DummyLoadCalibration.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            _LOGGER.warning("Ignoring invalid CLI dummy-load calibration in %s: %s", path, error)
            return None

    def _upgrade_legacy(self, request: BaseMeasurementRequest) -> DummyLoadCalibration | None:
        path = self._persistent_directory / _LEGACY_FILENAME
        if not path.exists():
            return None
        try:
            resistance = float(path.read_text(encoding="utf-8").strip())
            if resistance <= 0:
                raise ValueError("resistance must be positive")
        except (OSError, ValueError) as error:
            _LOGGER.warning("Ignoring invalid legacy dummy-load resistance in %s: %s", path, error)
            return None

        calibration = DummyLoadCalibration(
            description=_LEGACY_DESCRIPTION,
            resistance=resistance,
            calibrated_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
            power_meter_fingerprint=power_meter_fingerprint(request.power_meter),
        )
        self._write(calibration)
        path.unlink()
        _LOGGER.info("Upgraded legacy dummy-load resistance to %s", self._persistent_directory / _CALIBRATION_FILENAME)
        return calibration

    def _write(self, calibration: DummyLoadCalibration) -> None:
        self._persistent_directory.mkdir(parents=True, exist_ok=True)
        path = self._persistent_directory / _CALIBRATION_FILENAME
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(calibration.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(path)


def dummy_load_questions(
    measure_type: MeasureType,
    environment: CliEnvironment,
    store: CliDummyLoadCalibrationStore,
) -> list[Question]:
    """Build CLI questions for selecting or calibrating a resistive dummy load."""

    def matching_calibration(answers: dict[str, Any]) -> DummyLoadCalibration | None:
        if not answers.get(QUESTION_DUMMY_LOAD, False):
            return None
        return store.load(request_from_answers(measure_type, answers, environment))

    def mode_choices(answers: dict[str, Any]) -> list[tuple[str, str]]:
        calibration = matching_calibration(answers)
        choices: list[tuple[str, str]] = []
        if calibration is not None:
            choices.append(
                (
                    f"Use saved calibration: {calibration.description} ({calibration.resistance:.2f} Ω)",
                    "reuse",
                ),
            )
        choices.append(("Calibrate the connected dummy load", "calibrate"))
        return choices

    def description_default(answers: dict[str, Any]) -> str:
        calibration = matching_calibration(answers)
        return calibration.description if calibration is not None else "Resistive dummy load"

    return [
        dummy_load_enabled_question(),
        inquirer.List(
            name=QUESTION_DUMMY_LOAD_MODE,
            message="How do you want to prepare the dummy load?",
            choices=mode_choices,
            ignore=lambda answers: not answers.get(QUESTION_DUMMY_LOAD, False),
        ),
        inquirer.Text(
            name=QUESTION_DUMMY_LOAD_DESCRIPTION,
            message="Describe the connected dummy load",
            default=description_default,
            ignore=lambda answers: (
                not answers.get(QUESTION_DUMMY_LOAD, False) or answers.get(QUESTION_DUMMY_LOAD_MODE) == "reuse"
            ),
            validate=lambda _, current: bool(current.strip()),
        ),
    ]


def dummy_load_enabled_question() -> Question:
    """Ask whether this measurement should use a physical resistive dummy load."""

    return inquirer.Confirm(
        name=QUESTION_DUMMY_LOAD,
        message=(
            "Do you want to use a resistive dummy load? This helps measure standby power "
            "and low power levels accurately"
        ),
        default=False,
    )


def apply_dummy_load_answers(
    request: MeasurementRequest,
    answers: dict[str, Any],
    store: CliDummyLoadCalibrationStore,
) -> MeasurementRequest:
    """Attach the CLI dummy-load selection to a validated measurement request."""

    if not answers.get(QUESTION_DUMMY_LOAD, False):
        return request

    mode = str(answers.get(QUESTION_DUMMY_LOAD_MODE, "calibrate"))
    if mode == "reuse":
        calibration = store.load(request)
        if calibration is None:
            raise ValueError("The selected dummy-load calibration is no longer available for this power meter")
        dummy_load: DummyLoadCalibrationRequest | DummyLoadReuseRequest = DummyLoadReuseRequest(
            description=calibration.description,
            resistance=calibration.resistance,
        )
    else:
        description = str(answers.get(QUESTION_DUMMY_LOAD_DESCRIPTION, "")).strip()
        dummy_load = DummyLoadCalibrationRequest(description=description)

    data = request.model_dump(mode="json")
    data["dummy_load"] = dummy_load.model_dump(mode="json")
    return parse_measurement_request(data)
