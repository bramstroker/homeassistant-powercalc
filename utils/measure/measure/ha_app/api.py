from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
from typing import Annotated, cast

from fastapi import APIRouter, Body, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from measure.const import PARAMETER_LIMITS, MeasureType
from measure.controller.light.const import LutMode
from measure.ha_app.coordinator import MeasurementCoordinator, SessionConflictError
from measure.ha_app.preferences import AppPreferences
from measure.ha_app.preflight import ActiveSessionError, MeasurementPreflight, PreflightError
from measure.ha_app.registry import FieldControl, measurement_definitions, supported_light_modes
from measure.ha_app.service import MeasurementService
from measure.ha_app.session import ACTIVE_SESSION_STATES, SessionEvent, SessionSnapshot
from measure.ha_app.storage import SessionStorage
from measure.home_assistant import HomeAssistantManager
from measure.home_assistant_entities import (
    DeviceClass,
    EntityDescriptor,
    EntityDomain,
    HomeAssistantEntityCatalog,
)
from measure.powermeter.const import PowerMeterType
from measure.powermeter.dummy import DummyPowerMeter
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.hass import HassPowerMeter
from measure.powermeter.powermeter import PowerMeter
from measure.powermeter.shelly import ShellyPowerMeter
from measure.request import MeasurementRequest
from measure.tuning import MeasurementParameters

_LOGGER = logging.getLogger("measure")


class ErrorResponse(BaseModel):
    code: str
    message: str
    field: str | None = None


# Shared OpenAPI documentation for the JSON error body returned by every failed request.
_ERROR = {"model": ErrorResponse}
_NO_SESSION = "No measurement session"
MeasurementRequestPayload = Annotated[MeasurementRequest, Body(discriminator="measure_type")]


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


class FormFieldOption(BaseModel):
    value: str
    label: str
    entity_domain: str | None = None


class FormField(BaseModel):
    name: str
    label: str
    control: FieldControl
    required: bool = True
    entity_domains: list[str] = Field(default_factory=list)
    options: list[FormFieldOption] = Field(default_factory=list)
    default: str | int | bool | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None


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
        self.home_assistant = HomeAssistantManager(hass_url, hass_token)
        self.trusted_ingress_only = trusted_ingress_only
        self.storage = SessionStorage(data_root)
        self.coordinator = MeasurementCoordinator(
            self.storage,
            self._measurement_service,
        )

    def _measurement_service(self) -> MeasurementService:
        return MeasurementService(self.home_assistant)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        cast(AppContext, app.state.context).home_assistant.close()


def create_app(
    *,
    data_root: Path,
    hass_url: str = "ws://supervisor/core/websocket",
    hass_token: str | None = None,
    static_root: Path | None = None,
    trusted_ingress_only: bool | None = None,
) -> FastAPI:
    token = hass_token or os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN is required to start the Home Assistant app")
    if trusted_ingress_only is None:
        trusted_ingress_only = os.environ.get("MEASURE_TRUSTED_INGRESS_ONLY", "false").lower() == "true"
    context = AppContext(
        data_root=data_root,
        hass_url=hass_url,
        hass_token=token,
        trusted_ingress_only=trusted_ingress_only,
    )
    app = FastAPI(title="Powercalc Measure", version="0.1.0", docs_url=None, redoc_url=None, lifespan=_lifespan)
    app.state.context = context
    app.include_router(_router())

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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

    _register_error_handlers(app)

    assets = static_root or Path(__file__).parent.parent / "static"
    if assets.exists():
        assets_directory = assets / "assets"
        if assets_directory.exists():
            app.mount("/assets", StaticFiles(directory=assets_directory), name="assets")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(assets / "index.html")

    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        first = error.errors()[0] if error.errors() else {}
        location = first.get("loc", ())
        field = ".".join(str(part) for part in location if part != "body" and part not in MeasureType) or None
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


def _router() -> APIRouter:
    router = APIRouter(prefix="/api")
    _register_measurement_routes(router)
    _register_session_routes(router)
    return router


def _register_measurement_routes(router: APIRouter) -> None:  # noqa: C901
    @router.get("/capabilities")
    async def capabilities(request: Request) -> CapabilitiesResponse:
        defaults = MeasurementParameters()
        app_defaults = (await run_in_threadpool(_context(request).storage.load_settings)).measurement_defaults
        return CapabilitiesResponse(
            modes=list(supported_light_modes()),
            defaults={
                "sleep_time": app_defaults.sleep_time,
                "sample_count": app_defaults.sample_count,
                "sleep_time_sample": app_defaults.sleep_time_sample,
                "max_retries": app_defaults.max_retries,
                "max_nudges": app_defaults.max_nudges,
                "bri_bri_steps": defaults.bri_bri_steps,
                "ct_bri_steps": defaults.ct_bri_steps,
                "ct_mired_steps": defaults.ct_mired_steps,
                "hs_bri_steps": defaults.hs_bri_steps,
                "hs_hue_steps": defaults.hs_hue_steps,
                "hs_sat_steps": defaults.hs_sat_steps,
                "min_brightness": defaults.min_brightness,
                "sleep_initial": defaults.sleep_initial,
                "sleep_standby": defaults.sleep_standby,
                "effect_bri_steps": defaults.effect_bri_steps,
                "measure_time_effect": defaults.measure_time_effect,
                "measure_time_effect_min": defaults.measure_time_effect_min,
            },
            limits={name: {"min": minimum, "max": maximum} for name, (minimum, maximum) in PARAMETER_LIMITS.items()},
        )

    @router.get("/measure-definitions")
    async def measure_definitions() -> list[MeasureDefinition]:
        return _measure_definitions()

    @router.get("/settings")
    async def get_settings(request: Request) -> AppPreferences:
        return await run_in_threadpool(_context(request).storage.load_settings)

    @router.put("/settings", responses={400: _ERROR})
    async def update_settings(payload: AppPreferences, request: Request) -> AppPreferences:
        return await run_in_threadpool(_context(request).storage.save_settings, payload)

    @router.post("/settings/test-power-meter")
    async def test_power_meter(payload: AppPreferences, request: Request) -> PowerMeterTestResult:
        return await run_in_threadpool(_test_power_meter, _context(request), payload)

    @router.get("/entities", responses={400: _ERROR})
    async def entities(
        request: Request,
        domain: Annotated[EntityDomain | None, Query()] = None,
        device_class: Annotated[DeviceClass | None, Query()] = None,
    ) -> list[EntityDescriptor]:
        if (domain is None) == (device_class is None):
            raise HTTPException(status_code=400, detail="Specify exactly one entity filter")
        snapshot = await run_in_threadpool(
            HomeAssistantEntityCatalog(_context(request).home_assistant).load_snapshot,
        )
        return snapshot.select(domain=domain, device_class=device_class)

    @router.post("/preflight", responses={409: _ERROR, 422: _ERROR})
    async def preflight(payload: MeasurementRequestPayload, request: Request) -> PreflightResponse:
        return await run_in_threadpool(_preflight, _context(request), payload)

    @router.post("/sessions", status_code=201, responses={409: _ERROR, 422: _ERROR})
    async def start_session(payload: MeasurementRequestPayload, request: Request) -> dict[str, object]:
        context = _context(request)
        await run_in_threadpool(_preflight, context, payload)
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


def _measure_definitions() -> list[MeasureDefinition]:
    return [
        MeasureDefinition(
            measure_type=definition.kind,
            label=definition.label,
            description=definition.description,
            fields=[
                FormField(
                    name=field.name,
                    label=field.label,
                    control=field.control,
                    required=field.required,
                    entity_domains=list(field.entity_domains),
                    options=[
                        FormFieldOption(
                            value=option.value,
                            label=option.label,
                            entity_domain=option.entity_domain,
                        )
                        for option in field.options
                    ],
                    default=field.default,
                    minimum=field.minimum,
                    maximum=field.maximum,
                )
                for field in definition.fields
            ],
            supports_profile=definition.supports_profile,
            supports_resume=definition.supports_resume,
        )
        for definition in measurement_definitions()
    ]


def _test_power_meter(context: AppContext, settings: AppPreferences) -> PowerMeterTestResult:
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


def _build_test_power_meter(context: AppContext, settings: AppPreferences) -> PowerMeter:
    if settings.power_meter == PowerMeterType.DUMMY:
        return DummyPowerMeter()
    if settings.power_meter == PowerMeterType.SHELLY:
        if not settings.shelly_ip:
            raise PowerMeterError("Enter the Shelly IP address first")
        return ShellyPowerMeter(settings.shelly_ip)
    if not settings.default_power_entity_id:
        raise PowerMeterError("Select a power sensor first")
    return HassPowerMeter(
        context.home_assistant,
        call_update_entity=False,
        entity_id=settings.default_power_entity_id,
    )


def _preflight(context: AppContext, payload: MeasurementRequest) -> PreflightResponse:
    catalog = HomeAssistantEntityCatalog(context.home_assistant)
    snapshot = None

    def load_entities(
        domain: EntityDomain | None,
        device_class: DeviceClass | None,
    ) -> list[EntityDescriptor]:
        nonlocal snapshot
        if snapshot is None:
            snapshot = catalog.load_snapshot()
        return snapshot.select(domain=domain, device_class=device_class)

    try:
        result = MeasurementPreflight(
            has_active_session=lambda: _is_active(context.coordinator.current),
            verify_storage=context.storage.verify_writable,
            load_entities=load_entities,
        ).validate(payload)
    except ActiveSessionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except PreflightError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return PreflightResponse(
        valid=True,
        warnings=list(result.warnings),
        estimated_variations=result.estimated_variations,
        estimated_duration_seconds=result.estimated_duration_seconds,
        supported_modes=list(result.supported_modes) if result.supported_modes is not None else None,
    )


def _is_active(snapshot: SessionSnapshot | None) -> bool:
    return snapshot is not None and snapshot.state in ACTIVE_SESSION_STATES


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
        "summary": snapshot.summary,
        "operating_point": snapshot.operating_point,
        "request": request,
    }


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
    last_event_id = request.headers.get("last-event-id", "0")
    try:
        sequence = max(0, int(last_event_id))
    except ValueError:
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
                heartbeat = {
                    "sequence": snapshot.event_sequence,
                    "type": "heartbeat",
                    "data": {},
                    "snapshot": _snapshot_response(context, snapshot),
                }
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat, default=str)}\n\n"
        await asyncio.sleep(1)


def _encode_event(context: AppContext, event: SessionEvent) -> str:
    snapshot = context.coordinator.current
    payload: dict[str, object] = {
        "sequence": event.sequence,
        "type": event.type,
        "data": event.data,
    }
    if snapshot is not None:
        payload["snapshot"] = _snapshot_response(context, snapshot)
    return f"id: {event.sequence}\nevent: {event.type}\ndata: {json.dumps(payload, default=str)}\n\n"
