from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
import json
import logging
import math
import mimetypes
import os
from pathlib import Path
import re
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from homeassistant_api import Client
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from measure.const import MeasureType
from measure.controller.light.const import LutMode
from measure.coordinator import MeasurementCoordinator, SessionConflictError
from measure.powermeter.const import QUESTION_POWERMETER_ENTITY_ID, PowerMeterType
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.hass import HassPowerMeter
from measure.powermeter.powermeter import PowerMeter
from measure.powermeter.shelly import ShellyPowerMeter
from measure.request import LightMeasurementRequestModel, MeasurementRunRequestModel
from measure.service import MeasurementService
from measure.session import SessionEvent, SessionSnapshot, SessionState
from measure.settings import AppSettings
from measure.storage import SessionStorage

_LOGGER = logging.getLogger("measure")


class ErrorResponse(BaseModel):
    code: str
    message: str
    field: str | None = None


# Shared OpenAPI documentation for the JSON error body returned by every failed request.
_ERROR = {"model": ErrorResponse}
_NO_SESSION = "No measurement session"

# Entity domains that can be picked as the measurement device in the app.
DeviceDomain = Literal["light", "media_player", "fan", "vacuum"]


class EntityDescriptor(BaseModel):
    entity_id: str
    name: str
    state: str | None = None
    unit: str | None = None
    supported_modes: list[LutMode] | None = None
    effect_list: list[str] | None = None


class PreflightResponse(BaseModel):
    valid: bool
    warnings: list[str]
    estimated_variations: int | None = None
    estimated_duration_seconds: int | None = None
    supported_modes: list[LutMode] | None = None


class SessionFile(BaseModel):
    name: str
    size: int
    media_type: str


class CapabilitiesResponse(BaseModel):
    modes: list[LutMode]
    defaults: dict[str, int | float]
    limits: dict[str, dict[str, int | float]]


class FormField(BaseModel):
    name: str
    label: str
    control: Literal["entity", "number", "text", "boolean", "select"]
    required: bool = True
    entity_domain: str | None = None
    options: list[dict[str, str]] = []
    default: str | int | bool | None = None


class MeasureDefinition(BaseModel):
    measure_type: MeasureType
    label: str
    description: str
    fields: list[FormField]
    supports_profile: bool
    supports_resume: bool


class PowerMeterTestResult(BaseModel):
    success: bool
    power: float | None = None
    message: str | None = None


class AppContext:
    def __init__(
        self,
        *,
        data_root: Path,
        hass_url: str,
        hass_token: str,
        trusted_ingress_only: bool,
    ) -> None:
        self.hass_url = hass_url
        self.hass_token = hass_token
        self.trusted_ingress_only = trusted_ingress_only
        self.storage = SessionStorage(data_root)
        self.coordinator = MeasurementCoordinator(
            self.storage,
            self._measurement_service,
        )

    def _measurement_service(self) -> MeasurementService:
        settings = self.storage.load_settings()
        return MeasurementService(
            self.hass_url,
            self.hass_token,
            settings.power_meter,
            settings.shelly_ip,
        )

    def client(self) -> Client:
        return Client(self.hass_url, self.hass_token)


def create_app(
    *,
    data_root: Path,
    hass_url: str = "http://supervisor/core/api/",
    hass_token: str | None = None,
    static_root: Path | None = None,
    trusted_ingress_only: bool | None = None,
) -> FastAPI:
    token = hass_token or os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN is required to start the Home Assistant app")
    context = AppContext(
        data_root=data_root,
        hass_url=hass_url,
        hass_token=token,
        trusted_ingress_only=(os.environ.get("MEASURE_TRUSTED_INGRESS_ONLY", "false").lower() == "true")
        if trusted_ingress_only is None
        else trusted_ingress_only,
    )
    app = FastAPI(title="Powercalc Measure", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.context = context
    app.include_router(_router())

    @app.middleware("http")
    async def restrict_to_ingress(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_host = request.client.host if request.client else None
        if context.trusted_ingress_only and client_host != "172.30.32.2":
            error = ErrorResponse(code="ingress_required", message="Ingress access required")
            return JSONResponse(status_code=403, content=error.model_dump())
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        first = error.errors()[0] if error.errors() else {}
        location = first.get("loc", ())
        field = ".".join(str(part) for part in location if part != "body") or None
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                code="validation_error",
                message=str(first.get("msg", "Invalid request")),
                field=field,
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException) -> JSONResponse:
        detail = str(error.detail)
        code = {
            400: "bad_request",
            404: "not_found",
            409: "session_conflict",
            422: "preflight_failed",
        }.get(error.status_code, "request_failed")
        return JSONResponse(
            status_code=error.status_code,
            content=ErrorResponse(code=code, message=detail).model_dump(),
        )

    @app.exception_handler(Exception)
    async def internal_error(_: Request, error: Exception) -> JSONResponse:
        _LOGGER.exception("Unhandled measure app request error", exc_info=error)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(code="internal_error", message="Internal server error").model_dump(),
        )

    assets = static_root or Path(__file__).with_name("static")
    if assets.exists():
        assets_directory = assets / "assets"
        if assets_directory.exists():
            app.mount("/assets", StaticFiles(directory=assets_directory), name="assets")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(assets / "index.html")

    return app


def _router() -> APIRouter:
    router = APIRouter(prefix="/api")
    _register_measurement_routes(router)
    _register_session_routes(router)
    return router


def _register_measurement_routes(router: APIRouter) -> None:  # noqa: C901
    @router.get("/capabilities")
    async def capabilities() -> CapabilitiesResponse:
        return CapabilitiesResponse(
            modes=[LutMode.BRIGHTNESS, LutMode.COLOR_TEMP, LutMode.HS, LutMode.EFFECT],
            defaults={
                "sleep_time": 2,
                "sample_count": 1,
                "brightness_step": 5,
                "hue_step": 10,
                "saturation_step": 10,
                "color_temp_step": 5,
            },
            limits={
                "sleep_time": {"min": 0, "max": 120},
                "sample_count": {"min": 1, "max": 100},
            },
        )

    @router.get("/measure-definitions")
    async def measure_definitions() -> list[MeasureDefinition]:
        return _measure_definitions()

    @router.get("/settings")
    async def get_settings(request: Request) -> AppSettings:
        return await run_in_threadpool(_context(request).storage.load_settings)

    @router.put("/settings", responses={400: _ERROR})
    async def update_settings(payload: AppSettings, request: Request) -> AppSettings:
        return await run_in_threadpool(_context(request).storage.save_settings, payload)

    @router.post("/settings/test-power-meter")
    async def test_power_meter(payload: AppSettings, request: Request) -> PowerMeterTestResult:
        return await run_in_threadpool(_test_power_meter, _context(request), payload)

    @router.get("/entities", responses={400: _ERROR})
    async def entities(
        request: Request,
        domain: Annotated[DeviceDomain | None, Query()] = None,
        kind: Annotated[Literal["power", "voltage"] | None, Query()] = None,
    ) -> list[EntityDescriptor]:
        if (domain is None) == (kind is None):
            raise HTTPException(status_code=400, detail="Specify exactly one entity filter")
        return await run_in_threadpool(_load_entities, _context(request), domain, kind)

    @router.post("/preflight", responses={409: _ERROR, 422: _ERROR})
    async def preflight(payload: LightMeasurementRequestModel, request: Request) -> PreflightResponse:
        return await run_in_threadpool(_preflight, _context(request), payload)

    @router.post("/runs/preflight", responses={409: _ERROR, 422: _ERROR})
    async def preflight_run(payload: MeasurementRunRequestModel, request: Request) -> PreflightResponse:
        return await run_in_threadpool(_preflight_run, _context(request), payload)

    @router.post("/sessions", status_code=201, responses={409: _ERROR, 422: _ERROR})
    async def start_session(payload: LightMeasurementRequestModel, request: Request) -> dict[str, object]:
        context = _context(request)
        await run_in_threadpool(_preflight, context, payload)
        try:
            snapshot = context.coordinator.start(payload)
        except SessionConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _snapshot_response(context, snapshot)

    @router.post("/runs", status_code=201, responses={409: _ERROR, 422: _ERROR})
    async def start_run(payload: MeasurementRunRequestModel, request: Request) -> dict[str, object]:
        context = _context(request)
        await run_in_threadpool(_preflight_run, context, payload)
        try:
            snapshot = context.coordinator.start(payload)
        except SessionConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _snapshot_response(context, snapshot)


def _register_session_routes(router: APIRouter) -> None:  # noqa: C901
    @router.get("/session/current", responses={404: _ERROR})
    async def current_session(request: Request) -> dict[str, object]:
        context = _context(request)
        return _snapshot_response(context, _require_current_session(context))

    @router.delete("/session/current", status_code=202, responses={409: _ERROR})
    async def cancel_session(request: Request) -> dict[str, object]:
        context = _context(request)
        try:
            snapshot = context.coordinator.cancel()
        except SessionConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _snapshot_response(context, snapshot)

    @router.post("/session/current/confirm", responses={404: _ERROR, 409: _ERROR})
    async def confirm_session(request: Request) -> dict[str, object]:
        context = _context(request)
        try:
            snapshot = context.coordinator.confirm()
        except SessionConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _snapshot_response(context, snapshot)

    @router.post("/session/current/resume", responses={404: _ERROR, 409: _ERROR})
    async def resume_session(request: Request) -> dict[str, object]:
        context = _context(request)
        try:
            snapshot = context.coordinator.current
            if snapshot is None:
                raise SessionConflictError("There is no current session to resume")
            await run_in_threadpool(_preflight, context, context.storage.load_request(snapshot.id))
            snapshot = context.coordinator.resume()
        except SessionConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _snapshot_response(context, snapshot)

    @router.get("/session/current/files", responses={404: _ERROR})
    async def files(request: Request) -> list[SessionFile]:
        context = _context(request)
        snapshot = _require_current_session(context)
        return [
            _file_descriptor(context.storage.file_path(snapshot.id, name), name)
            for name in context.storage.list_files(snapshot.id)
        ]

    @router.get("/session/current/files/{name:path}", responses={404: _ERROR})
    async def download(name: str, request: Request) -> FileResponse:
        context = _context(request)
        snapshot = _require_current_session(context)
        try:
            path = context.storage.file_path(snapshot.id, name)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail="File not found") from error
        return FileResponse(path, filename=path.name)

    @router.get("/session/current/events", responses={404: _ERROR})
    async def events(request: Request) -> StreamingResponse:
        context = _context(request)
        _require_current_session(context)
        return StreamingResponse(_event_stream(request, context), media_type="text/event-stream")


def _context(request: Request) -> AppContext:
    return cast(AppContext, request.app.state.context)


def _require_current_session(context: AppContext) -> SessionSnapshot:
    snapshot = context.coordinator.current
    if snapshot is None:
        raise HTTPException(status_code=404, detail=_NO_SESSION)
    return snapshot


def _load_entities(
    context: AppContext,
    domain: DeviceDomain | None,
    kind: Literal["power", "voltage"] | None,
) -> list[EntityDescriptor]:
    all_entities = context.client().get_entities()
    selected_domain = domain or "sensor"
    if selected_domain not in all_entities:
        return []
    unit = {"power": "W", "voltage": "V"}.get(kind or "")
    result = [
        descriptor
        for entity in all_entities[selected_domain].entities.values()
        if (descriptor := _describe_entity(entity, domain, unit)) is not None
    ]
    return sorted(result, key=lambda item: (item.name.casefold(), item.entity_id))


def _describe_entity(entity: Any, domain: DeviceDomain | None, unit: str | None) -> EntityDescriptor | None:  # noqa: ANN401
    attributes = entity.state.attributes
    entity_unit = attributes.get("unit_of_measurement")
    if unit and entity_unit != unit:
        return None
    entity_state = str(entity.state.state)
    if entity_state.casefold() in {"unavailable", "unknown", "none"}:
        return None
    if unit and not _is_finite_number(entity_state):
        return None
    supported_modes = None
    if domain == "light":
        supported_modes = _supported_light_modes(attributes)
        if not supported_modes:
            return None
    return EntityDescriptor(
        entity_id=entity.entity_id,
        name=str(attributes.get("friendly_name", entity.entity_id)),
        state=entity_state,
        unit=str(entity_unit) if entity_unit else None,
        supported_modes=supported_modes,
        effect_list=list(attributes.get("effect_list", [])) or None,
    )


def _supported_light_modes(attributes: dict[str, Any]) -> list[LutMode]:
    values = set(attributes.get("supported_color_modes", []))
    modes = [mode for mode in (LutMode.COLOR_TEMP, LutMode.HS) if mode.value in values]
    if values - {"onoff"} or "brightness" in attributes:
        modes.insert(0, LutMode.BRIGHTNESS)
    if attributes.get("effect_list"):
        modes.append(LutMode.EFFECT)
    return modes


def _measure_definitions() -> list[MeasureDefinition]:
    power = FormField(name="powermeter_entity_id", label="Power sensor", control="entity", entity_domain="sensor")
    entity = lambda label, domain: FormField(name="entity_id", label=label, control="entity", entity_domain=domain)  # noqa: E731
    return [
        MeasureDefinition(
            measure_type=MeasureType.LIGHT,
            label="Light bulb(s)",
            description="Build a lookup-table power profile for a light.",
            fields=[power, entity("Light", "light")],
            supports_profile=True,
            supports_resume=True,
        ),
        MeasureDefinition(
            measure_type=MeasureType.SPEAKER,
            label="Smart speaker",
            description="Measure power across media-player volume levels.",
            fields=[
                power,
                entity("Media player", "media_player"),
                FormField(
                    name="disable_streaming",
                    label="Disable automatic pink-noise streaming",
                    control="boolean",
                    required=False,
                    default=False,
                ),
            ],
            supports_profile=True,
            supports_resume=False,
        ),
        MeasureDefinition(
            measure_type=MeasureType.RECORDER,
            label="Recorder",
            description="Record live power readings to a CSV file until cancelled.",
            fields=[
                power,
                FormField(name="export_filename", label="Export filename", control="text", default="record.csv"),
            ],
            supports_profile=False,
            supports_resume=False,
        ),
        MeasureDefinition(
            measure_type=MeasureType.AVERAGE,
            label="Average",
            description="Measure average power for a fixed duration.",
            fields=[power, FormField(name="duration", label="Duration (seconds)", control="number", default=60)],
            supports_profile=False,
            supports_resume=False,
        ),
        MeasureDefinition(
            measure_type=MeasureType.CHARGING,
            label="Charging device",
            description="Measure charging power against battery level.",
            fields=[
                power,
                FormField(
                    name="charging_device_type",
                    label="Charging device type",
                    control="select",
                    options=[
                        {"value": "vacuum_robot", "label": "Vacuum robot"},
                        {"value": "lawn_mower_robot", "label": "Lawn mower robot"},
                    ],
                ),
                entity("Charging device", "vacuum"),
            ],
            supports_profile=True,
            supports_resume=False,
        ),
        MeasureDefinition(
            measure_type=MeasureType.FAN,
            label="Fan",
            description="Measure fan power across percentage levels.",
            fields=[power, entity("Fan", "fan")],
            supports_profile=True,
            supports_resume=False,
        ),
    ]


def _test_power_meter(context: AppContext, settings: AppSettings) -> PowerMeterTestResult:
    """Take a single live reading from the configured power meter to confirm connectivity."""
    try:
        meter = _build_test_power_meter(context, settings)
        reading = meter.get_power(include_voltage=False)
    except PowerMeterError as error:
        return PowerMeterTestResult(success=False, message=str(error))
    except Exception as error:  # noqa: BLE001 - surface any connection/parsing failure to the user
        _LOGGER.debug("Power meter test failed", exc_info=True)
        return PowerMeterTestResult(success=False, message=str(error) or "Could not read from the power meter")
    return PowerMeterTestResult(success=True, power=round(reading.power, 2))


def _build_test_power_meter(context: AppContext, settings: AppSettings) -> PowerMeter:
    if settings.power_meter == PowerMeterType.DUMMY:
        return DummyPowerMeter()
    if settings.power_meter == PowerMeterType.SHELLY:
        if not settings.shelly_ip:
            raise PowerMeterError("Enter the Shelly IP address first")
        return ShellyPowerMeter(settings.shelly_ip)
    if not settings.default_power_entity_id:
        raise PowerMeterError("Select a power sensor first")
    meter = HassPowerMeter(context.hass_url, context.hass_token, call_update_entity=False)
    meter.process_answers({QUESTION_POWERMETER_ENTITY_ID: settings.default_power_entity_id})
    return meter


def _preflight_run(context: AppContext, payload: MeasurementRunRequestModel) -> PreflightResponse:
    current = context.coordinator.current
    if current is not None and current.state in {
        SessionState.VALIDATING,
        SessionState.READY,
        SessionState.AWAITING_CONFIRMATION,
        SessionState.RUNNING,
        SessionState.CANCELLING,
    }:
        raise HTTPException(status_code=409, detail="A measurement session is already active")
    try:
        context.storage.verify_writable()
    except OSError as error:
        raise HTTPException(status_code=422, detail="Persistent app storage is not writable") from error
    definition = next((item for item in _measure_definitions() if item.measure_type == payload.measure_type), None)
    if definition is None:
        raise HTTPException(status_code=422, detail="Selected measurement type is unavailable")
    missing = [field.label for field in definition.fields if field.required and not payload.answers.get(field.name)]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {', '.join(missing)}")
    return PreflightResponse(valid=True, warnings=[])


def _preflight(context: AppContext, payload: LightMeasurementRequestModel) -> PreflightResponse:
    current = context.coordinator.current
    if current is not None and current.state in {
        SessionState.VALIDATING,
        SessionState.READY,
        SessionState.AWAITING_CONFIRMATION,
        SessionState.RUNNING,
        SessionState.CANCELLING,
    }:
        raise HTTPException(status_code=409, detail="A measurement session is already active")
    try:
        context.storage.verify_writable()
    except OSError as error:
        raise HTTPException(status_code=422, detail="Persistent app storage is not writable") from error
    lights = {entity.entity_id: entity for entity in _load_entities(context, "light", None)}
    powers = {entity.entity_id: entity for entity in _load_entities(context, None, "power")}
    voltages = {entity.entity_id: entity for entity in _load_entities(context, None, "voltage")}
    if payload.light_entity_id not in lights:
        raise HTTPException(status_code=422, detail="Selected light entity is unavailable")
    uses_hass_meter = context.storage.load_settings().power_meter == PowerMeterType.HASS
    if uses_hass_meter and payload.power_entity_id not in powers:
        raise HTTPException(status_code=422, detail="Selected power entity is unavailable or not measured in W")
    if uses_hass_meter and payload.voltage_entity_id and payload.voltage_entity_id not in voltages:
        raise HTTPException(status_code=422, detail="Selected voltage entity is unavailable or not measured in V")
    light = lights[payload.light_entity_id]
    supported = set(light.supported_modes or [])
    requested = set(payload.modes)
    if not requested.issubset(supported):
        raise HTTPException(status_code=422, detail="Selected light does not advertise every requested mode")
    estimated = _estimated_variations(payload, len(light.effect_list or []))
    return PreflightResponse(
        valid=True,
        warnings=[],
        estimated_variations=estimated,
        estimated_duration_seconds=round(estimated * payload.sleep_time * payload.sample_count),
        supported_modes=sorted(supported, key=str),
    )


def _estimated_variations(payload: LightMeasurementRequestModel, effect_count: int = 0) -> int:
    count = 0
    if LutMode.BRIGHTNESS in payload.modes:
        count += 255 // payload.brightness_step + 1
    if LutMode.COLOR_TEMP in payload.modes:
        count += (255 // payload.brightness_step + 1) * (350 // payload.color_temp_step + 1)
    if LutMode.HS in payload.modes:
        count += (
            (255 // payload.brightness_step + 1) * (360 // payload.hue_step + 1) * (100 // payload.saturation_step + 1)
        )
    if LutMode.EFFECT in payload.modes:
        count += max(1, effect_count) * (255 // payload.brightness_step + 1)
    return count


def _snapshot_response(context: AppContext, snapshot: SessionSnapshot) -> dict[str, object]:
    request = context.storage.load_request(snapshot.id).model_dump(mode="json")
    return {
        "session_id": snapshot.id,
        "state": snapshot.state,
        "phase": snapshot.state,
        "mode": snapshot.mode,
        "progress": {
            "completed": snapshot.completed,
            "total": snapshot.total,
            "percent": snapshot.progress,
            "estimated_remaining_seconds": _duration_seconds(snapshot.estimated_remaining),
        },
        "warnings": list(snapshot.warnings),
        "error": snapshot.error,
        "request": request,
    }


def _is_finite_number(value: str) -> bool:
    try:
        return math.isfinite(float(value))
    except ValueError:
        return False


def _duration_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([hms])", value)
    if match is None:
        return None
    multiplier = {"h": 3600, "m": 60, "s": 1}[match.group(2)]
    return round(float(match.group(1)) * multiplier)


def _file_descriptor(path: Path, name: str) -> SessionFile:
    return SessionFile(
        name=name,
        size=path.stat().st_size,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )


async def _event_stream(request: Request, context: AppContext) -> AsyncIterator[str]:
    sequence = 0
    while not await request.is_disconnected():
        events = context.coordinator.events_since(sequence)
        if events:
            for event in events:
                sequence = max(sequence, event.sequence)
                yield _encode_event(context, event)
        else:
            snapshot = context.coordinator.current
            if snapshot is not None:
                heartbeat = {"type": "heartbeat", "snapshot": _snapshot_response(context, snapshot)}
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat, default=str)}\n\n"
        await asyncio.sleep(1)


def _encode_event(context: AppContext, event: SessionEvent) -> str:
    snapshot = context.coordinator.current
    payload: dict[str, object] = {"type": event.type, **event.data}
    if snapshot is not None:
        payload["snapshot"] = _snapshot_response(context, snapshot)
    return f"event: {event.type}\ndata: {json.dumps(payload, default=str)}\n\n"
