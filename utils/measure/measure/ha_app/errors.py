import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from measure.const import MeasureType
from measure.ha_app.api_models import ErrorResponse
from measure.ha_app.contribution.models import (
    ContributionApiError,
    ContributionApiErrorCode,
)

_LOGGER = logging.getLogger("measure")


class DocumentedHTTPException(HTTPException):
    """HTTP failure with a structured documentation action for API clients."""

    def __init__(self, *, status_code: int, detail: str, help_url: str, help_label: str) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.help_url = help_url
        self.help_label = help_label


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


def register_error_handlers(app: FastAPI) -> None:
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
        content = ErrorResponse(
            code=code,
            message=detail,
            help_url=getattr(error, "help_url", None),
            help_label=getattr(error, "help_label", None),
        ).model_dump()
        if content["help_url"] is None or content["help_label"] is None:
            content.pop("help_url")
            content.pop("help_label")
        return JSONResponse(
            status_code=error.status_code,
            content=content,
        )

    @app.exception_handler(ContributionApiError)
    async def contribution_error(_: Request, error: ContributionApiError) -> JSONResponse:
        status_code = _CONTRIBUTION_STATUS_CODES.get(error.code, 500)
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(code=error.code.value, message=str(error), field=error.field).model_dump(),
        )

    @app.exception_handler(Exception)
    async def internal_error(_: Request, error: Exception) -> JSONResponse:
        # Not lexically inside an `except` block, so `.exception()` trips LOG004.
        # `.error()` with an explicit exc_info logs at the same level with the traceback.
        _LOGGER.error("Unhandled measure app request error", exc_info=error)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(code="internal_error", message="Internal server error").model_dump(),
        )
