import asyncio
from collections.abc import AsyncIterator
import json
import mimetypes
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from measure.ha_app.api_models import (
    ERROR_RESPONSE,
    CalibrationSampleResponse,
    MeasurementRequestPayload,
    SessionEventResponse,
    SessionFile,
    SessionPlots,
    SessionProgressResponse,
    SessionSnapshotResponse,
    SessionSummary,
)
from measure.ha_app.context import AppContext, app_context, require_session
from measure.ha_app.coordinator import SessionConflictError
from measure.ha_app.diagnostics import DIAGNOSTIC_EVENT_LIMIT, build_session_diagnostics
from measure.ha_app.routes.measurement import (
    apply_fast_test_mode,
    run_preflight,
)
from measure.ha_app.session import (
    ACTIVE_SESSION_STATES,
    RESUMABLE_SESSION_STATES,
    SessionEvent,
    SessionSnapshot,
    SessionState,
    is_active_session,
)
from measure.ha_app.storage import SESSION_LOAD_ERRORS
from measure.visualization import build_session_plots

router = APIRouter()


@router.post("/sessions", status_code=201, responses={409: ERROR_RESPONSE, 422: ERROR_RESPONSE})
async def start_session(payload: MeasurementRequestPayload, request: Request) -> SessionSnapshotResponse:
    context = app_context(request)
    prepared = await run_in_threadpool(apply_fast_test_mode, context, payload)
    await run_in_threadpool(run_preflight, context, prepared)
    try:
        snapshot = context.coordinator.start(prepared)
    except SessionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _snapshot_response(context, snapshot)


@router.get("/sessions")
async def sessions(request: Request) -> list[SessionSummary]:
    context = app_context(request)
    snapshots = await run_in_threadpool(context.coordinator.sessions)
    summaries = [await run_in_threadpool(_session_summary, context, snapshot) for snapshot in snapshots]
    return sorted(summaries, key=lambda item: not item.active)


@router.get("/sessions/{session_id}", responses={404: ERROR_RESPONSE})
async def session(session_id: str, request: Request) -> SessionSnapshotResponse:
    context = app_context(request)
    return _snapshot_response(context, require_session(context, session_id))


@router.delete("/sessions/{session_id}", status_code=204, responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE})
async def delete_session(session_id: str, request: Request) -> Response:
    context = app_context(request)
    require_session(context, session_id)
    try:
        await run_in_threadpool(context.coordinator.delete, session_id)
    except SessionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(status_code=204)


@router.post("/sessions/{session_id}/cancel", status_code=202, responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE})
async def cancel_session(session_id: str, request: Request) -> SessionSnapshotResponse:
    return _cancel_session(app_context(request), session_id)


@router.post("/sessions/{session_id}/confirm", responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE})
async def confirm_session(session_id: str, request: Request) -> SessionSnapshotResponse:
    return _confirm_session(app_context(request), session_id)


@router.post("/sessions/{session_id}/resume", responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE, 422: ERROR_RESPONSE})
async def resume_session(session_id: str, request: Request) -> SessionSnapshotResponse:
    return await _resume_session(app_context(request), session_id)


@router.post("/sessions/{session_id}/analyse", responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE})
async def analyse_session(session_id: str, request: Request) -> SessionSnapshotResponse:
    context = app_context(request)
    require_session(context, session_id)
    try:
        snapshot = await run_in_threadpool(context.coordinator.analyse, session_id)
    except SessionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _snapshot_response(context, snapshot)


@router.post(
    "/sessions/{session_id}/record-more", responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE, 422: ERROR_RESPONSE}
)
async def record_more(session_id: str, request: Request) -> SessionSnapshotResponse:
    context = app_context(request)
    snapshot = require_session(context, session_id)
    if snapshot.state in ACTIVE_SESSION_STATES or not context.storage.can_analyse(session_id):
        raise HTTPException(status_code=409, detail="The requested session has no profile recording to extend")
    await run_in_threadpool(run_preflight, context, context.storage.load_request(session_id))
    try:
        snapshot = context.coordinator.record_more(session_id)
    except SessionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _snapshot_response(context, snapshot)


@router.get("/sessions/{session_id}/files", responses={404: ERROR_RESPONSE})
async def session_files(session_id: str, request: Request) -> list[SessionFile]:
    context = app_context(request)
    snapshot = require_session(context, session_id)
    return _session_files(context, snapshot)


@router.get("/sessions/{session_id}/plots", responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE})
async def session_plots(session_id: str, request: Request) -> SessionPlots:
    context = app_context(request)
    return await _session_plots(context, require_session(context, session_id))


@router.get("/sessions/{session_id}/files/{name:path}", responses={404: ERROR_RESPONSE})
async def session_download(session_id: str, name: str, request: Request) -> FileResponse:
    context = app_context(request)
    return _session_download(context, require_session(context, session_id), name)


@router.get("/sessions/{session_id}/diagnostics", responses={404: ERROR_RESPONSE})
async def session_diagnostics(session_id: str, request: Request) -> Response:
    context = app_context(request)
    return _session_diagnostics(context, require_session(context, session_id))


@router.get("/sessions/{session_id}/events", responses={404: ERROR_RESPONSE})
async def session_events(session_id: str, request: Request) -> StreamingResponse:
    context = app_context(request)
    require_session(context, session_id)
    return StreamingResponse(_event_stream(request, context, session_id), media_type="text/event-stream")


def _cancel_session(context: AppContext, session_id: str) -> SessionSnapshotResponse:
    try:
        snapshot = context.coordinator.cancel(session_id)
    except SessionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _snapshot_response(context, snapshot)


def _confirm_session(context: AppContext, session_id: str) -> SessionSnapshotResponse:
    try:
        snapshot = context.coordinator.confirm(session_id)
    except SessionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _snapshot_response(context, snapshot)


async def _resume_session(context: AppContext, session_id: str) -> SessionSnapshotResponse:
    snapshot = require_session(context, session_id)
    await run_in_threadpool(run_preflight, context, context.storage.load_request(snapshot.id))
    try:
        snapshot = context.coordinator.resume(snapshot.id)
    except SessionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _snapshot_response(context, snapshot)


def _session_files(context: AppContext, snapshot: SessionSnapshot) -> list[SessionFile]:
    return [
        _file_descriptor(context.storage.file_path(snapshot.id, name), name)
        for name in context.storage.list_files(snapshot.id)
    ]


async def _session_plots(context: AppContext, snapshot: SessionSnapshot) -> SessionPlots:
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


def _session_download(context: AppContext, snapshot: SessionSnapshot, name: str) -> FileResponse:
    try:
        path = context.storage.file_path(snapshot.id, name)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=404, detail="File not found") from error
    return FileResponse(path, filename=path.name)


def _session_diagnostics(context: AppContext, snapshot: SessionSnapshot) -> Response:
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


def _snapshot_response(context: AppContext, snapshot: SessionSnapshot) -> SessionSnapshotResponse:
    return SessionSnapshotResponse(
        session_id=snapshot.id,
        state=snapshot.state,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        phase=snapshot.phase,
        confirmation_message=snapshot.confirmation_message,
        confirmation_action=snapshot.confirmation_action,
        mode=snapshot.mode,
        progress=SessionProgressResponse(
            completed=snapshot.completed,
            total=snapshot.total,
            skipped=snapshot.skipped,
            percent=snapshot.progress,
            estimated_remaining_seconds=_duration_seconds(snapshot.estimated_remaining),
        ),
        warnings=list(snapshot.warnings),
        error=snapshot.error,
        summary=snapshot.summary,
        operating_point=snapshot.operating_point,
        calibration_sample=(
            CalibrationSampleResponse(**snapshot.calibration_sample)
            if snapshot.calibration_sample is not None
            else None
        ),
        entity_states=snapshot.entity_states,
        can_analyse=snapshot.state not in ACTIVE_SESSION_STATES and context.storage.can_analyse(snapshot.id),
        request=context.storage.load_request(snapshot.id),
    )


def _session_summary(context: AppContext, snapshot: SessionSnapshot) -> SessionSummary:
    request = context.storage.load_request(snapshot.id)
    current = context.coordinator.current
    return SessionSummary(
        session_id=snapshot.id,
        state=snapshot.state,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        measure_type=request.measure_type,
        model_id=request.model_id,
        product_name=(
            request.session_name or request.product_name or ", ".join(request.controlled_entity_ids) or "Measurement"
        ),
        measure_device=request.measure_device,
        completed=snapshot.completed,
        total=snapshot.total,
        percent=snapshot.progress,
        can_resume=context.storage.can_resume(snapshot.id) and snapshot.state in RESUMABLE_SESSION_STATES,
        file_count=len(context.storage.list_files(snapshot.id)),
        size=context.storage.session_size(snapshot.id),
        active=current is not None and current.id == snapshot.id and is_active_session(snapshot),
    )


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


async def _event_stream(request: Request, context: AppContext, session_id: str) -> AsyncIterator[str]:
    last_event_id = request.headers.get("last-event-id", "0")
    try:
        sequence = max(0, int(last_event_id))
    except ValueError:
        sequence = 0
    while not await request.is_disconnected():
        events = context.coordinator.events_since(sequence, session_id)
        if events:
            for event in events:
                sequence = max(sequence, event.sequence)
                yield _encode_event(context, event, session_id)
        else:
            try:
                snapshot = context.coordinator.get(session_id)
            except SESSION_LOAD_ERRORS:
                return
            heartbeat = SessionEventResponse(
                sequence=snapshot.event_sequence,
                type="heartbeat",
                data={},
                snapshot=_snapshot_response(context, snapshot),
            )
            yield f"event: heartbeat\ndata: {heartbeat.model_dump_json()}\n\n"
        await asyncio.sleep(1)


def _encode_event(context: AppContext, event: SessionEvent, session_id: str) -> str:
    try:
        snapshot = context.coordinator.get(session_id)
    except SESSION_LOAD_ERRORS:
        snapshot = None
    payload = SessionEventResponse(
        sequence=event.sequence,
        type=event.type,
        data=event.data,
        snapshot=_snapshot_response(context, snapshot) if snapshot is not None else None,
    )
    exclude = {"snapshot"} if snapshot is None else None
    return f"id: {event.sequence}\nevent: {event.type}\ndata: {payload.model_dump_json(exclude=exclude)}\n\n"
