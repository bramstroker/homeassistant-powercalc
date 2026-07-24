from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
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

from measure.assembler import MeasurementAssembler
from measure.const import PARAMETER_LIMITS, MeasureType
from measure.controller.light.const import LutMode
from measure.dummy_load import DummyLoadCalibration, power_meter_fingerprint
from measure.execution import ImmediateInteraction
from measure.ha_app.contribution import (
    ConnectPatRequest,
    ContributionApiCoordinator,
    ContributionApiError,
    ContributionApiErrorCode,
    ContributionAuthStatus,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
    ContributionStatus,
    ContributionSubmissionResult,
    ContributionSubmitRequest,
    DeviceFlowPollResponse,
    DeviceFlowStartResponse,
)
from measure.ha_app.coordinator import MeasurementCoordinator, SessionConflictError
from measure.ha_app.diagnostics import DIAGNOSTIC_EVENT_LIMIT, build_session_diagnostics
from measure.ha_app.preferences import AppPreferences
from measure.ha_app.preflight import ActiveSessionError, MeasurementPreflight, PreflightError
from measure.ha_app.registry import FieldControl, measurement_definitions, supported_light_modes
from measure.ha_app.service import MeasurementService
from measure.ha_app.session import ACTIVE_SESSION_STATES, SessionEvent, SessionSnapshot, SessionState
from measure.ha_app.shelly_discovery import ShellyDiscoveryResponse, ShellyDiscoveryService
from measure.ha_app.storage import SessionStorage
from measure.home_assistant import HomeAssistantManager
from measure.home_assistant_entities import (
    DeviceClass,
    EntityDescriptor,
    EntityDomain,
    HomeAssistantEntityCatalog,
)
from measure.powermeter.const import PowerMeterType
from measure.powermeter.diagnostics import DiagnosticStatus, PowerMeterDiagnostic, PowerMeterDiagnostics
from measure.powermeter.errors import PowerMeterError
from measure.powermeter.powermeter import PowerMeter
from measure.powermeter.spec import DummyPowerMeterSpec, HassPowerMeterSpec, PowerMeterSpec, ShellyPowerMeterSpec
from measure.request import MeasurementRequest
from measure.tuning import MeasurementParameters
from measure.version import measure_version
from measure.visualization import PlotSpec, build_session_plots

_LOGGER = logging.getLogger("measure")


class ErrorResponse(BaseModel):
    code: str
    message: str
    field: str | None = None


# Shared OpenAPI documentation for the JSON error body returned by every failed request.
_ERROR = {"model": ErrorResponse}

_CONTRIBUTION_STATUS_CODES = {
    ContributionApiErrorCode.AUTH_UNAVAILABLE: 401,
    ContributionApiErrorCode.SESSION_REQUIRED: 404,
    ContributionApiErrorCode.FLOW_NOT_FOUND: 404,
    ContributionApiErrorCode.SESSION_NOT_READY: 409,
    ContributionApiErrorCode.PREVIEW_REQUIRED: 409,
    ContributionApiErrorCode.CONTRIBUTION_ACTIVE: 409,
    ContributionApiErrorCode.ARTIFACTS_REQUIRED: 422,
    ContributionApiErrorCode.INVALID_METADATA: 422,
    ContributionApiErrorCode.SUBMISSION_FAILED: 502,
}
_NO_SESSION = "No measurement session"
MeasurementRequestPayload = Annotated[MeasurementRequest, Body(discriminator="measure_type")]


class PreflightResponse(BaseModel):
    valid: bool
    warnings: list[str]
    estimated_variations: int | None = None
    estimated_duration_seconds: int | None = None
    supported_modes: list[LutMode] | None = None
    power_meter_diagnostic: PowerMeterDiagnostic | None = None
    battery_level_entity_id: str | None = None
    battery_level_attribute: str | None = None


class EntityCatalogResponse(BaseModel):
    lights: list[EntityDescriptor]
    powers: list[EntityDescriptor]
    voltages: list[EntityDescriptor]


class SessionFile(BaseModel):
    name: str
    size: int
    media_type: str


class SessionPlots(BaseModel):
    partial: bool
    plots: list[PlotSpec]
    warnings: list[str]


class CapabilitiesResponse(BaseModel):
    modes: list[LutMode]
    defaults: dict[str, int | float]
    limits: dict[str, dict[str, int | float]]
    developer_mode: bool = False
    fast_test_mode: bool = False


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
    confirmation_action: str | None
    fields: list[FormField]
    supports_profile: bool
    supports_resume: bool


class AppContext:
    def __init__(
        self,
        *,
        data_root: Path,
        hass_url: str,
        hass_token: str,
        trusted_ingress_only: bool,
        developer_mode: bool = False,
    ) -> None:
        self.home_assistant = HomeAssistantManager(hass_url, hass_token)
        self.trusted_ingress_only = trusted_ingress_only
        self.developer_mode = developer_mode
        self.storage = SessionStorage(data_root)
        self.power_meter_diagnostics = PowerMeterDiagnostics(self.build_power_meter)
        self.contribution = ContributionApiCoordinator(self.storage)
        self.coordinator = MeasurementCoordinator(
            self.storage,
            self._measurement_service,
        )

    def _measurement_service(self) -> MeasurementService:
        return MeasurementService(self.home_assistant, self.storage)

    def build_power_meter(self, spec: PowerMeterSpec) -> PowerMeter:
        return MeasurementAssembler(
            ImmediateInteraction(),
            home_assistant=self.home_assistant,
        ).build_power_meter(spec)


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
    developer_mode: bool = False,
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
        developer_mode=developer_mode,
    )
    app = FastAPI(
        title="Powercalc Measure",
        version=measure_version(),
        docs_url=None,
        redoc_url=None,
        lifespan=_lifespan,
    )
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
        # /health is probed by the container HEALTHCHECK from localhost and
        # exposes no data, so it bypasses the ingress source check.
        if context.trusted_ingress_only and request.url.path != "/health" and client_host != "172.30.32.2":
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

    @app.exception_handler(ContributionApiError)
    async def contribution_error(_: Request, error: ContributionApiError) -> JSONResponse:
        status_code = _CONTRIBUTION_STATUS_CODES.get(error.code, 500)
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(code=error.code.value, message=str(error)).model_dump(),
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
    _register_contribution_routes(router)
    return router


def _register_measurement_routes(router: APIRouter) -> None:  # noqa: C901
    @router.get("/capabilities")
    async def capabilities(request: Request) -> CapabilitiesResponse:
        context = _context(request)
        defaults = MeasurementParameters()
        settings = await run_in_threadpool(context.storage.load_settings)
        return CapabilitiesResponse(
            modes=list(supported_light_modes()),
            defaults={name: getattr(defaults, name) for name in PARAMETER_LIMITS}
            | settings.measurement_defaults.model_dump(),
            limits={name: {"min": minimum, "max": maximum} for name, (minimum, maximum) in PARAMETER_LIMITS.items()},
            developer_mode=context.developer_mode,
            fast_test_mode=context.developer_mode and settings.fast_test_mode,
        )

    @router.get("/measure-definitions")
    async def measure_definitions() -> list[MeasureDefinition]:
        return _measure_definitions()

    @router.get("/settings")
    async def get_settings(request: Request) -> AppPreferences:
        return await run_in_threadpool(_context(request).storage.load_settings)

    @router.put("/settings", responses={400: _ERROR})
    async def update_settings(payload: AppPreferences, request: Request) -> AppPreferences:
        context = _context(request)
        if payload.fast_test_mode and not context.developer_mode:
            raise HTTPException(status_code=400, detail="Fast test mode requires developer mode")
        return await run_in_threadpool(context.storage.save_settings, payload)

    @router.post("/settings/test-power-meter")
    async def test_power_meter(payload: AppPreferences, request: Request) -> PowerMeterDiagnostic:
        return await run_in_threadpool(_test_power_meter, _context(request), payload)

    @router.get("/power-meters/shelly")
    async def discover_shelly_power_meters(request: Request) -> ShellyDiscoveryResponse:
        return await ShellyDiscoveryService(_context(request).home_assistant).discover()

    @router.get("/dummy-load/calibration")
    async def dummy_load_calibration(request: Request) -> DummyLoadCalibration | None:
        return await run_in_threadpool(_matching_dummy_load_calibration, _context(request))

    @router.get("/entity-catalog")
    async def entity_catalog(request: Request) -> EntityCatalogResponse:
        snapshot = await run_in_threadpool(
            HomeAssistantEntityCatalog(_context(request).home_assistant).load_snapshot,
        )
        return EntityCatalogResponse(
            lights=snapshot.select(domain=EntityDomain.LIGHT),
            powers=snapshot.select(device_class=DeviceClass.POWER),
            voltages=snapshot.select(device_class=DeviceClass.VOLTAGE),
        )

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
        context = _context(request)
        prepared = await run_in_threadpool(_apply_fast_test_mode, context, payload)
        return await run_in_threadpool(_preflight, context, prepared)

    @router.post("/sessions", status_code=201, responses={409: _ERROR, 422: _ERROR})
    async def start_session(payload: MeasurementRequestPayload, request: Request) -> dict[str, object]:
        context = _context(request)
        prepared = await run_in_threadpool(_apply_fast_test_mode, context, payload)
        await run_in_threadpool(_preflight, context, prepared)
        try:
            snapshot = context.coordinator.start(prepared)
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

    @router.get("/session/current/plots", responses={404: _ERROR, 409: _ERROR})
    async def plots(request: Request) -> SessionPlots:
        context = _context(request)
        snapshot = _require_current_session(context)
        if snapshot.state in ACTIVE_SESSION_STATES:
            raise HTTPException(status_code=409, detail="Plots are available after the measurement stops")
        names = context.storage.list_files(snapshot.id)
        paths = {name: context.storage.file_path(snapshot.id, name) for name in names}
        result = await run_in_threadpool(
            build_session_plots,
            context.storage.load_request(snapshot.id),
            paths,
        )
        return SessionPlots(
            partial=snapshot.state is not SessionState.COMPLETED,
            plots=list(result.plots),
            warnings=list(result.warnings),
        )

    @router.get("/session/current/files/{name:path}", responses={404: _ERROR})
    async def download(name: str, request: Request) -> FileResponse:
        context = _context(request)
        snapshot = _require_current_session(context)
        try:
            path = context.storage.file_path(snapshot.id, name)
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail="File not found") from error
        return FileResponse(path, filename=path.name)

    @router.get("/session/current/diagnostics", responses={404: _ERROR})
    async def diagnostics(request: Request) -> Response:
        context = _context(request)
        snapshot = _require_current_session(context)
        files = [
            _file_descriptor(context.storage.file_path(snapshot.id, name), name).model_dump()
            for name in context.storage.list_files(snapshot.id)
        ]
        events = context.storage.load_events(snapshot.id, limit=DIAGNOSTIC_EVENT_LIMIT + 1)
        events_truncated = len(events) > DIAGNOSTIC_EVENT_LIMIT
        payload = build_session_diagnostics(
            snapshot,
            context.storage.load_request(snapshot.id),
            events[-DIAGNOSTIC_EVENT_LIMIT:],
            files,
            events_truncated=events_truncated,
        )
        filename = f"powercalc-measure-diagnostics-{snapshot.id[:8]}.json"
        return Response(
            content=json.dumps(payload, indent=2, default=str),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/session/current/events", responses={404: _ERROR})
    async def events(request: Request) -> StreamingResponse:
        context = _context(request)
        _require_current_session(context)
        return StreamingResponse(_event_stream(request, context), media_type="text/event-stream")


def _register_contribution_routes(router: APIRouter) -> None:
    @router.get("/contribution/auth")
    async def contribution_auth_status(request: Request) -> ContributionAuthStatus:
        return await run_in_threadpool(_context(request).contribution.auth_status)

    @router.put("/contribution/auth")
    async def contribution_connect_pat(payload: ConnectPatRequest, request: Request) -> ContributionAuthStatus:
        return await run_in_threadpool(_context(request).contribution.connect_pat, payload.token)

    @router.delete("/contribution/auth")
    async def contribution_disconnect(request: Request) -> ContributionAuthStatus:
        return await run_in_threadpool(_context(request).contribution.disconnect)

    @router.post("/contribution/auth/device", responses={401: _ERROR})
    async def contribution_device_start(request: Request) -> DeviceFlowStartResponse:
        return await run_in_threadpool(_context(request).contribution.start_device_flow)

    @router.post("/contribution/auth/device/{flow_id}", responses={401: _ERROR, 404: _ERROR})
    async def contribution_device_poll(flow_id: str, request: Request) -> DeviceFlowPollResponse:
        return await run_in_threadpool(_context(request).contribution.poll_device_flow, flow_id)

    @router.get("/contribution/status")
    async def contribution_status(request: Request) -> ContributionStatus:
        return _context(request).contribution.status()

    @router.get("/session/current/contribution", responses={404: _ERROR, 409: _ERROR})
    async def current_contribution_draft(request: Request) -> ContributionPreviewResponse:
        context = _context(request)
        snapshot = _require_current_session(context)
        return await run_in_threadpool(context.contribution.draft, snapshot)

    @router.post(
        "/session/current/contribution/preview",
        responses={404: _ERROR, 409: _ERROR, 422: _ERROR, 502: _ERROR},
    )
    async def current_contribution_preview(
        payload: ContributionPreviewRequest,
        request: Request,
    ) -> ContributionPreviewResponse:
        context = _context(request)
        snapshot = _require_current_session(context)
        return await run_in_threadpool(context.contribution.preview, snapshot, payload)

    @router.post(
        "/session/current/contribution",
        responses={401: _ERROR, 404: _ERROR, 409: _ERROR, 502: _ERROR},
    )
    async def current_contribution_submit(
        payload: ContributionSubmitRequest,
        request: Request,
    ) -> ContributionSubmissionResult:
        context = _context(request)
        snapshot = _require_current_session(context)
        return await run_in_threadpool(context.contribution.submit, snapshot, payload)


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
            confirmation_action=definition.confirmation_action,
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


def _test_power_meter(context: AppContext, settings: AppPreferences) -> PowerMeterDiagnostic:
    """Validate connectivity and measurement quality for the configured meter."""
    try:
        spec = _power_meter_spec(settings)
    except PowerMeterError as error:
        message = str(error)
        return PowerMeterDiagnostic(
            success=False,
            status=DiagnosticStatus.POOR,
            precision_status=DiagnosticStatus.UNSUPPORTED,
            update_interval_status=DiagnosticStatus.UNSUPPORTED,
            messages=[message],
            message=message,
        )
    return context.power_meter_diagnostics.evaluate(spec, force=True)


def _power_meter_spec(settings: AppPreferences) -> PowerMeterSpec:
    if settings.power_meter == PowerMeterType.DUMMY:
        return DummyPowerMeterSpec()
    if settings.power_meter == PowerMeterType.SHELLY:
        if not settings.shelly_ip:
            raise PowerMeterError("Enter the Shelly IP address first")
        return ShellyPowerMeterSpec(device_ip=settings.shelly_ip)
    if not settings.default_power_entity_id:
        raise PowerMeterError("Select a power sensor first")
    return HassPowerMeterSpec(entity_id=settings.default_power_entity_id)


def _matching_dummy_load_calibration(context: AppContext) -> DummyLoadCalibration | None:
    calibration = context.storage.load_dummy_load_calibration()
    if calibration is None:
        return None
    try:
        spec = _power_meter_spec(context.storage.load_settings())
    except PowerMeterError:
        return None
    if isinstance(spec, HassPowerMeterSpec):
        snapshot = HomeAssistantEntityCatalog(context.home_assistant).load_snapshot()
        spec = spec.model_copy(
            update={
                "voltage_entity_id": snapshot.related_entity_id(spec.entity_id, DeviceClass.VOLTAGE),
            },
        )
    return calibration if calibration.power_meter_fingerprint == power_meter_fingerprint(spec) else None


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
            diagnose_power_meter=context.power_meter_diagnostics.evaluate,
            developer_mode=context.developer_mode,
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
        power_meter_diagnostic=result.power_meter_diagnostic,
        battery_level_entity_id=result.battery_level_entity_id,
        battery_level_attribute=result.battery_level_attribute,
    )


def _apply_fast_test_mode(context: AppContext, request: MeasurementRequest) -> MeasurementRequest:
    settings = context.storage.load_settings()
    controller = request.controller
    supported_dummy_controller = controller is not None and controller.is_dummy
    enabled = (
        context.developer_mode
        and settings.fast_test_mode
        and isinstance(request.power_meter, DummyPowerMeterSpec)
        and supported_dummy_controller
    )
    parameters = replace(request.parameters, fast_test_mode=False)
    if enabled:
        parameters = replace(
            request.parameters,
            fast_test_mode=True,
            sleep_time=0,
            sleep_time_sample=0,
            sample_count=1,
            sleep_initial=0,
            sleep_standby=0,
            sleep_time_hue=0,
            sleep_time_sat=0,
            sleep_time_ct=0,
            sleep_time_effect_change=0,
            measure_time_effect=1,
            measure_time_effect_min=1,
        )
    return request.model_copy(update={"fast_test_mode": enabled, "parameters": parameters})


def _is_active(snapshot: SessionSnapshot | None) -> bool:
    return snapshot is not None and snapshot.state in ACTIVE_SESSION_STATES


def _snapshot_response(context: AppContext, snapshot: SessionSnapshot) -> dict[str, object]:
    request = context.storage.load_request(snapshot.id).model_dump(mode="json")
    return {
        "session_id": snapshot.id,
        "state": snapshot.state,
        "phase": snapshot.phase,
        "confirmation_message": snapshot.confirmation_message,
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
