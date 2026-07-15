from __future__ import annotations

import json

from measure.ha_app.diagnostics import REDACTED, build_session_diagnostics
from measure.ha_app.session import SessionEvent, SessionEventType, SessionSnapshot, SessionState
from measure.powermeter.spec import ShellyPowerMeterSpec
from measure.request import AverageMeasurementRequest


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
