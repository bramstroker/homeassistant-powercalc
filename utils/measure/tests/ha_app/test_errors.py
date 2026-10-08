from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from measure.ha_app.errors import register_error_handlers
from measure.ha_app.light_probe import LightLoadProbeError
from measure.ha_app.preflight import ActiveSessionError, PreflightError
import pytest


def _error_response(error: Exception) -> Response:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/test")
    async def fail() -> None:
        raise error

    with TestClient(app, raise_server_exceptions=False) as client:
        return client.get("/test")


@pytest.mark.parametrize(
    "error,status,code",
    [
        pytest.param(ActiveSessionError("Already running"), 409, "session_conflict", id="active-session"),
        pytest.param(PreflightError("No storage"), 422, "preflight_failed", id="preflight"),
        pytest.param(LightLoadProbeError("Probe failed"), 422, "preflight_failed", id="probe"),
        pytest.param(
            LightLoadProbeError("Probe failed", help_url="https://example.com/guide"),
            422,
            "preflight_failed",
            id="incomplete-help",
        ),
    ],
)
def test_preparation_errors_keep_the_http_contract(error: Exception, status: int, code: str) -> None:
    response = _error_response(error)

    assert response.status_code == status
    assert response.json() == {"code": code, "message": str(error), "field": None}


def test_probe_error_keeps_documentation_action() -> None:
    response = _error_response(
        LightLoadProbeError("Load too low", help_url="https://example.com/guide", help_label="Read guide"),
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "preflight_failed",
        "message": "Load too low",
        "field": None,
        "help_url": "https://example.com/guide",
        "help_label": "Read guide",
    }


def test_unexpected_error_hides_internal_details() -> None:
    response = _error_response(RuntimeError("Internal details"))

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert response.json()["message"] == "Internal server error"
