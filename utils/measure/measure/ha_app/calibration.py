"""Background dummy-load calibration, independent of HTTP connection lifetime."""

from collections.abc import Callable
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, replace
from enum import StrEnum
import logging
from threading import Event, Lock, Thread
from uuid import uuid4

from measure.cancellation import MeasurementCancelledError
from measure.dummy_load import DummyLoadCalibration
from measure.request import MeasurementRequest
from measure.utils.clock import utc_now

_LOGGER = logging.getLogger(__name__)


class CalibrationStatus(StrEnum):
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class CalibrationJob:
    id: str
    session_id: str
    started_at: str
    status: CalibrationStatus = CalibrationStatus.RUNNING
    calibration: DummyLoadCalibration | None = None
    error: str | None = None


class CalibrationJobs:
    """Keep the latest operation per session discoverable after a page reload."""

    def __init__(
        self,
        reserve_devices: Callable[[], AbstractContextManager[None]],
        calibrate: Callable[[MeasurementRequest, Event], DummyLoadCalibration],
        save: Callable[[DummyLoadCalibration], DummyLoadCalibration],
    ) -> None:
        self._reserve_devices = reserve_devices
        self._calibrate = calibrate
        self._save = save
        self._lock = Lock()
        self._jobs: dict[str, CalibrationJob] = {}
        self._cancelled = Event()
        self._worker: Thread | None = None

    def get(self, session_id: str) -> CalibrationJob | None:
        with self._lock:
            return self._jobs.get(session_id)

    def start(self, session_id: str, request: MeasurementRequest) -> CalibrationJob:
        # Acquire before returning 202, so competing starts fail synchronously.
        reservation = ExitStack()
        reservation.enter_context(self._reserve_devices())
        try:
            with self._lock:
                job = CalibrationJob(str(uuid4()), session_id, utc_now())
                self._jobs[session_id] = job
                self._cancelled = Event()
                self._worker = Thread(target=self._run, args=(job, request, reservation, self._cancelled), daemon=True)
                self._worker.start()
            return job
        except BaseException:
            with self._lock:
                self._jobs.pop(session_id, None)
                self._worker = None
            reservation.close()
            raise

    def cancel(self, session_id: str, job_id: str) -> CalibrationJob:
        with self._lock:
            job = self._jobs.get(session_id)
            if job is None or job.id != job_id:
                raise KeyError(job_id)
            if job.status in {CalibrationStatus.RUNNING, CalibrationStatus.CANCELLING}:
                self._cancelled.set()
                job = replace(job, status=CalibrationStatus.CANCELLING)
                self._jobs[session_id] = job
            return job

    def shutdown(self) -> None:
        self._cancelled.set()
        if self._worker is not None:
            self._worker.join()

    def _run(self, job: CalibrationJob, request: MeasurementRequest, reservation: ExitStack, cancelled: Event) -> None:
        try:
            calibration = self._calibrate(request, cancelled)
            # Serialize cancellation with saving the completed result.
            with self._lock:
                if cancelled.is_set():
                    raise MeasurementCancelledError("Calibration cancelled")
                self._save(calibration)
                result = replace(job, status=CalibrationStatus.COMPLETED, calibration=calibration)
        except MeasurementCancelledError:
            result = replace(job, status=CalibrationStatus.CANCELLED)
        except Exception as error:  # Background failures must become an observable terminal state.
            _LOGGER.exception("Dummy-load calibration failed for session %s", job.session_id)
            result = replace(job, status=CalibrationStatus.FAILED, error=str(error))
        finally:
            with self._lock:
                self._jobs[job.session_id] = result
                reservation.close()
