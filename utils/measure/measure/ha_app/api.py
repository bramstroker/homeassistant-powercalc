from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from measure.ha_app.access import is_loopback_address, trusted_ingress_only_enabled
from measure.ha_app.api_models import ErrorResponse
from measure.ha_app.context import AppContext
from measure.ha_app.errors import register_error_handlers
from measure.ha_app.routes import contribution, measurement, sessions
from measure.ha_app.status import MeasureStatusPublisher
from measure.utils.version import measure_version


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    context = cast(AppContext, app.state.context)
    status_publisher = MeasureStatusPublisher(context.home_assistant, context.coordinator)
    await status_publisher.async_start()
    try:
        yield
    finally:
        await status_publisher.async_stop()
        await run_in_threadpool(context.calibration_jobs.shutdown)
        context.home_assistant.close()


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
        trusted_ingress_only = trusted_ingress_only_enabled()
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
    for router in (measurement.router, sessions.router, contribution.router):
        app.include_router(router, prefix="/api")

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.middleware("http")
    async def restrict_access(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_host = request.client.host if request.client else None
        if context.trusted_ingress_only:
            allowed = client_host == "172.30.32.2"
            code, message = "ingress_required", "Ingress access required"
        else:
            allowed = is_loopback_address(client_host)
            code, message = "local_access_required", "Local access required"
        # /health is probed by the container HEALTHCHECK from localhost and
        # exposes no data, so it bypasses the ingress source check.
        if request.url.path != "/health" and not allowed:
            error = ErrorResponse(code=code, message=message)
            return JSONResponse(status_code=403, content=error.model_dump())
        return await call_next(request)

    register_error_handlers(app)

    _mount_frontend(app, static_root or Path(__file__).parent.parent / "static")
    return app


def _mount_frontend(app: FastAPI, assets: Path) -> None:
    if not assets.exists():
        return
    assets_directory = assets / "assets"
    if assets_directory.exists():
        app.mount("/assets", StaticFiles(directory=assets_directory), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(
            assets / "index.html",
            headers={"Cache-Control": "no-store, max-age=0"},
        )
