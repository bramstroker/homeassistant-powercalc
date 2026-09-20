import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from measure.ha_app.api import create_app
from measure.ha_app.coordinator import MeasurementCoordinator, SessionConflictError
from measure.ha_app.routes.sessions import _encode_event, _event_stream
from measure.ha_app.session import SessionEvent, SessionEventType, SessionSnapshot, SessionState
from measure.powermeter.spec import DummyPowerMeterSpec
from measure.request import AverageMeasurementRequest
import pytest


@pytest.fixture
def session_client(tmp_path: Path) -> TestClient:
    app = create_app(data_root=tmp_path, hass_token="test-token", trusted_ingress_only=False)  # noqa: S106
    context = app.state.context
    snapshot = SessionSnapshot(
        id="session", state=SessionState.RESUMABLE, created_at="now", updated_at="now", event_sequence=3
    )
    context.storage.create(snapshot, AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()))
    context.coordinator = MagicMock(spec=MeasurementCoordinator)
    context.coordinator.get.return_value = snapshot
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.mark.parametrize(
    "action,status,state",
    [
        ("cancel", 202, SessionState.CANCELLING),
        ("confirm", 200, SessionState.RUNNING),
        ("resume", 200, SessionState.READY),
    ],
)
def test_session_controls_return_updated_snapshot(
    session_client: TestClient, action: str, status: int, state: SessionState
) -> None:
    context = session_client.app.state.context
    coordinator = context.coordinator
    operation = getattr(coordinator, action)
    operation.return_value = replace(coordinator.get.return_value, state=state, phase="Updated")
    order = MagicMock()
    order.attach_mock(operation, "operate")

    with patch("measure.ha_app.routes.sessions.run_preflight") as preflight:
        order.attach_mock(preflight, "preflight")
        response = session_client.post(f"/api/sessions/session/{action}")

    assert response.status_code == status
    assert response.json()["session_id"] == "session"
    assert response.json()["state"] == state.value
    assert response.json()["phase"] == "Updated"
    expected = [call.operate("session")]
    if action == "resume":
        expected.insert(0, call.preflight(context, context.storage.load_request("session")))
    assert order.mock_calls == expected


@pytest.mark.parametrize("action", ["cancel", "confirm", "resume"])
def test_session_controls_translate_conflicts_to_http_409(session_client: TestClient, action: str) -> None:
    operation = getattr(session_client.app.state.context.coordinator, action)
    operation.side_effect = SessionConflictError("Session cannot be changed")

    with patch("measure.ha_app.routes.sessions.run_preflight"):
        response = session_client.post(f"/api/sessions/session/{action}")

    assert response.status_code == 409
    assert "Session cannot be changed" in response.text
    operation.assert_called_once_with("session")


def test_resume_does_not_launch_after_failed_preflight(session_client: TestClient) -> None:
    context = session_client.app.state.context
    with patch(
        "measure.ha_app.routes.sessions.run_preflight",
        side_effect=HTTPException(status_code=422, detail="Device unavailable"),
    ) as preflight:
        response = session_client.post("/api/sessions/session/resume")

    assert response.status_code == 422
    assert "Device unavailable" in response.text
    preflight.assert_called_once_with(context, context.storage.load_request("session"))
    context.coordinator.resume.assert_not_called()


def test_resume_missing_session_does_not_run_preflight(session_client: TestClient) -> None:
    context = session_client.app.state.context
    context.coordinator.get.side_effect = FileNotFoundError
    with patch("measure.ha_app.routes.sessions.run_preflight") as preflight:
        response = session_client.post("/api/sessions/missing/resume")

    assert response.status_code == 404
    preflight.assert_not_called()
    context.coordinator.resume.assert_not_called()


@pytest.mark.parametrize("last_event_id,sequence", [(None, 0), ("invalid", 0), ("-5", 0), ("2", 2), ("99", 99)])
def test_event_stream_replays_then_sends_heartbeat_and_stops_on_disconnect(
    session_client: TestClient, last_event_id: str | None, sequence: int
) -> None:
    context = session_client.app.state.context
    events = [
        SessionEvent(2, SessionEventType.LOG, "now", {"message": "Measuring"}),
        SessionEvent(3, SessionEventType.PROGRESS, "now", {"completed": 1, "total": 2}),
    ]
    context.coordinator.events_since.side_effect = lambda after, _: [
        event for event in events if event.sequence > after
    ]
    request = MagicMock(spec=Request)
    request.headers = {"last-event-id": last_event_id} if last_event_id is not None else {}
    request.is_disconnected = AsyncMock(side_effect=[False, False, True])

    async def collect() -> list[str]:
        return [chunk async for chunk in _event_stream(request, context, "session")]

    with patch("measure.ha_app.routes.sessions.asyncio.sleep", new_callable=AsyncMock) as sleep:
        chunks = asyncio.run(collect())

    replayed = [event for event in events if event.sequence > sequence]
    for chunk, event in zip(chunks[: len(replayed)], replayed, strict=True):
        lines = chunk.splitlines()
        assert lines[0] == f"id: {event.sequence}"
        assert lines[1] == f"event: {event.type.value}"
        payload = json.loads(lines[2].removeprefix("data: "))
        assert payload["sequence"] == event.sequence
        assert payload["data"] == event.data
        assert payload["snapshot"]["session_id"] == "session"
        assert chunk.endswith("\n\n")
    heartbeats = chunks[len(replayed) :]
    assert len(heartbeats) == (1 if replayed else 2)
    for heartbeat in heartbeats:
        assert heartbeat.startswith("event: heartbeat\ndata: ")
        payload = json.loads(heartbeat.splitlines()[1].removeprefix("data: "))
        assert payload["type"] == "heartbeat"
        assert payload["sequence"] == 3
        assert payload["snapshot"]["state"] == "resumable"
        assert heartbeat.endswith("\n\n")
    assert context.coordinator.events_since.call_args_list == [
        call(sequence, "session"),
        call(max(sequence, 3), "session"),
    ]
    assert sleep.await_args_list == [call(1), call(1)]


def test_event_stream_does_not_poll_after_disconnect(session_client: TestClient) -> None:
    context = session_client.app.state.context
    request = MagicMock(spec=Request, headers={})
    request.is_disconnected = AsyncMock(return_value=True)

    async def collect() -> list[str]:
        return [chunk async for chunk in _event_stream(request, context, "session")]

    assert asyncio.run(collect()) == []
    context.coordinator.events_since.assert_not_called()


@pytest.mark.parametrize("error", [FileNotFoundError, ValueError])
def test_event_stream_stops_when_session_disappears(session_client: TestClient, error: type[Exception]) -> None:
    context = session_client.app.state.context
    context.coordinator.events_since.return_value = []
    context.coordinator.get.side_effect = error
    request = MagicMock(spec=Request, headers={})
    request.is_disconnected = AsyncMock(return_value=False)

    async def collect() -> list[str]:
        return [chunk async for chunk in _event_stream(request, context, "session")]

    with patch("measure.ha_app.routes.sessions.asyncio.sleep", new_callable=AsyncMock) as sleep:
        assert asyncio.run(collect()) == []
    context.coordinator.events_since.assert_called_once_with(0, "session")
    sleep.assert_not_awaited()


def test_event_encoding_preserves_event_when_snapshot_disappears(session_client: TestClient) -> None:
    context = session_client.app.state.context
    context.coordinator.get.side_effect = FileNotFoundError
    event = SessionEvent(4, SessionEventType.LOG, "now", {"message": "first\nsecond"})

    encoded = _encode_event(context, event, "session")

    assert encoded.startswith("id: 4\nevent: log\ndata: ")
    assert encoded.endswith("\n\n")
    assert len(encoded.splitlines()) == 4
    payload = json.loads(encoded.splitlines()[2].removeprefix("data: "))
    assert payload == {"sequence": 4, "type": "log", "data": {"message": "first\nsecond"}}


def test_events_endpoint_returns_event_stream(session_client: TestClient) -> None:
    async def finite_stream(request: Request, context: object, session_id: str) -> AsyncIterator[str]:
        assert session_id == "session"
        assert request.headers["last-event-id"] == "3"
        yield "id: 4\nevent: log\ndata: {}\n\n"

    with patch("measure.ha_app.routes.sessions._event_stream", side_effect=finite_stream):
        response = session_client.get("/api/sessions/session/events", headers={"Last-Event-ID": "3"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == "id: 4\nevent: log\ndata: {}\n\n"


def test_events_endpoint_rejects_missing_session(session_client: TestClient) -> None:
    session_client.app.state.context.coordinator.get.side_effect = FileNotFoundError
    with patch("measure.ha_app.routes.sessions._event_stream") as stream:
        response = session_client.get("/api/sessions/missing/events")

    assert response.status_code == 404
    stream.assert_not_called()
