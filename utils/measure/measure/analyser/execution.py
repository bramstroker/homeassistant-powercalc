from collections.abc import Mapping
import json
import logging
from pathlib import Path

from measure.analyser.service import RecorderAnalyser, analysis_context_for
from measure.files import write_json_atomic
from measure.model import write_model_json
from measure.request import RecorderMeasurementRequest

_LOGGER = logging.getLogger("measure")

ANALYSER_FILENAME = "analyser.json"
_LEGACY_ANALYSIS_FILENAME = "analysis.json"

_ANALYSIS_SUMMARY_KEYS = frozenset(
    {
        "Recording analysis",
        "Recording analysis reason",
        "Profile analysis",
        "Profile analysis reason",
        "Analysed feature",
        "Validation MAE",
        "Validation coverage",
    },
)


class RecorderAnalysisExecution:
    """Turn an existing recorder artifact into analysis and profile output."""

    def __init__(self, analyser: RecorderAnalyser | None = None) -> None:
        self.analyser = analyser or RecorderAnalyser()

    def run(
        self,
        request: RecorderMeasurementRequest,
        output_directory: Path,
        *,
        summary: Mapping[str, str] | None = None,
        voltages: list[float] | None = None,
    ) -> dict[str, str]:
        """Analyse the persisted recording while always preserving its raw samples."""

        model_path = output_directory / "model.json"
        retained_voltages = voltages if voltages is not None else _load_existing_voltages(model_path)
        try:
            context = analysis_context_for(request)
            analysis = self.analyser.analyse(output_directory / request.export_filename, context)
            write_json_atomic(output_directory / ANALYSER_FILENAME, analysis.to_dict())
            (output_directory / _LEGACY_ANALYSIS_FILENAME).unlink(missing_ok=True)
            if analysis.model_ready and analysis.model_config_fragment is not None:
                write_model_json(
                    output_directory,
                    standby_power=analysis.standby_power,
                    name=request.model_name,
                    measure_device=request.measure_device,
                    parameters=request.parameters,
                    extra_json_data={
                        "device_type": context.device_type,
                        **analysis.model_config_fragment.to_dict(),
                    },
                    voltages=retained_voltages,
                )
            else:
                model_path.unlink(missing_ok=True)
                if analysis.reason:
                    _LOGGER.warning("Profile was not created: %s", analysis.reason)
            for warning in analysis.warnings:
                _LOGGER.warning("Recording analysis: %s", warning)
            return _replace_analysis_summary(summary, analysis.summary())
        except Exception as error:  # noqa: BLE001 - raw recording must survive optional analysis failures
            reason = f"Recording analysis failed: {error}"
            _LOGGER.warning(reason)
            model_path.unlink(missing_ok=True)
            write_json_atomic(
                output_directory / ANALYSER_FILENAME,
                {
                    "schema_version": 1,
                    "status": "insufficient_data",
                    "sample_count": 0,
                    "reason": reason,
                },
            )
            (output_directory / _LEGACY_ANALYSIS_FILENAME).unlink(missing_ok=True)
            return _replace_analysis_summary(
                summary,
                {
                    "Recording analysis": "Failed",
                    "Recording analysis reason": reason,
                },
            )


def _replace_analysis_summary(
    summary: Mapping[str, str] | None,
    analysis_summary: Mapping[str, str],
) -> dict[str, str]:
    retained = {key: value for key, value in (summary or {}).items() if key not in _ANALYSIS_SUMMARY_KEYS}
    return {**retained, **analysis_summary}


def _load_existing_voltages(path: Path) -> list[float] | None:
    """Keep the original recording's voltage range when regenerating its profile."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        voltage_range = value["voltage_range"]
        return [float(voltage_range["min"]), float(voltage_range["max"])]
    except FileNotFoundError, KeyError, TypeError, ValueError:
        return None
