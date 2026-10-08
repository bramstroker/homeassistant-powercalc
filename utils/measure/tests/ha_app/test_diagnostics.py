import json

from measure.ha_app import diagnostics
from measure.ha_app.diagnostics import REDACTED, build_session_diagnostics
from measure.ha_app.session import SessionEvent, SessionEventType, SessionSnapshot, SessionState
from measure.powermeter.spec import DummyPowerMeterSpec, ShellyPowerMeterSpec
from measure.request import AverageMeasurementRequest
import pytest


def test_diagnostics_redact_network_addresses_from_request_and_logs() -> None:
    device_ip = "192.0.2.42"
    api_key = "secret-key"
    request = AverageMeasurementRequest(power_meter=ShellyPowerMeterSpec(device_ip=device_ip))
    snapshot = SessionSnapshot(
        id="session-id",
        state=SessionState.FAILED,
        created_at="2026-07-15T12:00:00Z",
        updated_at="2026-07-15T12:01:00Z",
        error=f"Could not connect to {device_ip}",
    )
    events = (
        SessionEvent(
            sequence=1,
            type=SessionEventType.LOG,
            created_at="2026-07-15T12:00:30Z",
            data={
                "api_key": api_key,
                "message": f"Connecting to power meter at {device_ip} using {api_key}",
            },
        ),
    )

    report = build_session_diagnostics(snapshot, request, events, ())
    serialized = json.dumps(report)

    assert device_ip not in serialized
    assert api_key not in serialized
    assert REDACTED in serialized


@pytest.mark.parametrize("key", ["PASSWORD", "secret", "token", "device_ip", "api_key", "ha_token"])
def test_diagnostics_redact_nested_credentials_and_their_mentions(key: str) -> None:
    credentials = {"primary": "long-secret-value", "alternatives": ["long-secret", ("other-secret",)]}
    event = SessionEvent(
        sequence=1,
        type=SessionEventType.WARNING,
        created_at="2026-09-18T12:00:00Z",
        data={
            "configuration": {key: credentials},
            "message": "long-secret-value / long-secret / other-secret",
            "optional_token": None,
        },
    )
    snapshot = SessionSnapshot(
        id="session-id",
        state=SessionState.FAILED,
        created_at=event.created_at,
        updated_at=event.created_at,
    )

    report = build_session_diagnostics(
        snapshot,
        AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()),
        [event],
        [],
    )

    assert report["logs"][0]["data"] == {
        "configuration": {key: REDACTED},
        "message": f"{REDACTED} / {REDACTED} / {REDACTED}",
        "optional_token": None,
    }
    assert event.data["configuration"][key] == credentials
    assert event.data["message"] == "long-secret-value / long-secret / other-secret"


def test_diagnostics_include_all_events_but_only_log_events_in_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = "2026-09-18T12:00:00Z"
    monkeypatch.setattr(diagnostics, "utc_now", lambda: timestamp)
    monkeypatch.setattr(diagnostics, "measure_version", lambda: "1.2.3")
    snapshot = SessionSnapshot(
        id="session-id",
        state=SessionState.RUNNING,
        created_at=timestamp,
        updated_at=timestamp,
    )
    events = [
        SessionEvent(sequence=index, type=event_type, created_at=timestamp, data={"message": event_type.value})
        for index, event_type in enumerate(SessionEventType, start=1)
    ]
    files = [{"name": "record.jsonl", "size": 42}]

    report = build_session_diagnostics(
        snapshot,
        AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()),
        events,
        files,
        events_truncated=True,
    )

    assert [event["type"] for event in report["events"]] == list(SessionEventType)
    assert [event["type"] for event in report["logs"]] == [
        SessionEventType.WARNING,
        SessionEventType.LOG,
        SessionEventType.CHECKPOINT,
    ]
    assert report["generated_at"] == timestamp
    assert report["measure_version"] == "1.2.3"
    assert report["events_truncated"] is True
    assert report["files"] == files


def test_diagnostics_remain_available_when_version_cannot_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> str:
        raise OSError("Version file unavailable")

    monkeypatch.setattr(diagnostics, "measure_version", fail)
    snapshot = SessionSnapshot(
        id="session-id",
        state=SessionState.FAILED,
        created_at="2026-09-18T12:00:00Z",
        updated_at="2026-09-18T12:00:00Z",
    )

    report = build_session_diagnostics(
        snapshot,
        AverageMeasurementRequest(power_meter=DummyPowerMeterSpec()),
        [],
        [],
    )

    assert report["measure_version"] == "unknown"
