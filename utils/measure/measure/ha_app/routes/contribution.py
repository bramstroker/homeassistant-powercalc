from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from measure.ha_app.api_models import ERROR_RESPONSE
from measure.ha_app.context import get_app_context, require_session
from measure.ha_app.contribution.models import (
    ConnectPatRequest,
    ContributionAuthStatus,
    ContributionPreviewRequest,
    ContributionPreviewResponse,
    ContributionStatus,
    ContributionSubmissionResult,
    ContributionSubmitRequest,
    DeviceFlowPollResponse,
    DeviceFlowStartResponse,
)

router = APIRouter()


@router.get("/contribution/auth")
async def contribution_auth_status(request: Request) -> ContributionAuthStatus:
    return await run_in_threadpool(get_app_context(request).contribution.auth_status)


@router.put("/contribution/auth")
async def contribution_connect_pat(payload: ConnectPatRequest, request: Request) -> ContributionAuthStatus:
    return await run_in_threadpool(get_app_context(request).contribution.connect_pat, payload.token)


@router.delete("/contribution/auth")
async def contribution_disconnect(request: Request) -> ContributionAuthStatus:
    return await run_in_threadpool(get_app_context(request).contribution.disconnect)


@router.post("/contribution/auth/device", responses={401: ERROR_RESPONSE})
async def contribution_device_start(request: Request) -> DeviceFlowStartResponse:
    return await run_in_threadpool(get_app_context(request).contribution.start_device_flow)


@router.post("/contribution/auth/device/{flow_id}", responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE})
async def contribution_device_poll(flow_id: str, request: Request) -> DeviceFlowPollResponse:
    return await run_in_threadpool(get_app_context(request).contribution.poll_device_flow, flow_id)


@router.get("/contribution/status")
async def contribution_status(request: Request) -> ContributionStatus:
    return get_app_context(request).contribution.status()


@router.get("/sessions/{session_id}/contribution", responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE})
async def contribution_draft(session_id: str, request: Request) -> ContributionPreviewResponse:
    context = get_app_context(request)
    return await run_in_threadpool(context.contribution.draft, require_session(context, session_id))


@router.post(
    "/sessions/{session_id}/contribution/preview",
    responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE, 422: ERROR_RESPONSE, 502: ERROR_RESPONSE},
)
async def contribution_preview(
    session_id: str,
    payload: ContributionPreviewRequest,
    request: Request,
) -> ContributionPreviewResponse:
    context = get_app_context(request)
    return await run_in_threadpool(
        context.contribution.preview,
        require_session(context, session_id),
        payload,
    )


@router.post(
    "/sessions/{session_id}/contribution",
    responses={401: ERROR_RESPONSE, 404: ERROR_RESPONSE, 409: ERROR_RESPONSE, 502: ERROR_RESPONSE},
)
async def contribution_submit(
    session_id: str,
    payload: ContributionSubmitRequest,
    request: Request,
) -> ContributionSubmissionResult:
    context = get_app_context(request)
    return await run_in_threadpool(
        context.contribution.submit,
        require_session(context, session_id),
        payload,
    )


@router.get(
    "/sessions/{session_id}/contribution/{job_id}/profile.zip",
    responses={404: ERROR_RESPONSE, 409: ERROR_RESPONSE},
)
async def contribution_profile_archive(session_id: str, job_id: str, request: Request) -> Response:
    context = get_app_context(request)
    content = await run_in_threadpool(
        context.contribution.prepared_archive,
        require_session(context, session_id),
        job_id,
    )
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="powercalc-profile.zip"'},
    )
