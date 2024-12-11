from unittest.mock import patch

import pytest
from measure.powermeter.errors import ApiConnectionError
from measure.powermeter.shelly import ShellyPowerMeter
from requests import RequestException

from ..conftest import MockRequestsGetFactory  # noqa

DEFAULT_SHELLY_IP = "192.168.1.200"
SHELLY_ENDPOINT = f"http://{DEFAULT_SHELLY_IP}/shelly"


def test_api_gen1(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    status_response = {
        "meters": [
            {
                "power": 20.00,
                "overpower": 23.78,
                "is_valid": True,
                "timestamp": 1733039773,
                "counters": [1, 2, 3],
                "total": 4,
            },
        ],
    }

    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 1}, 200),
            f"http://{DEFAULT_SHELLY_IP}/status": (status_response, 200),
        },
    )

    pm = ShellyPowerMeter(DEFAULT_SHELLY_IP)
    power = pm.get_power()
    assert power.power == 20.00
    assert power.updated == 1733039773


def test_api_gen2_switch_endpoint(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 2}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Switch.GetStatus?id=0": ({"apower": 20.00}, 200),
        },
    )

    pm = ShellyPowerMeter(DEFAULT_SHELLY_IP)
    with patch("time.time", return_value=1733039773):
        power = pm.get_power()

    assert power.power == 20.00
    assert power.updated == 1733039773


def test_api_gen2_status_endpoint(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    """When the Switch.GetStatus endpoint is not available, we should use the PM1.Status endpoint."""
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 2}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Switch.GetStatus?id=0": ({}, 404),
            f"http://{DEFAULT_SHELLY_IP}/rpc/PM1.GetStatus?id=0": ({"apower": 20.00}, 200),
        },
    )

    pm = ShellyPowerMeter(DEFAULT_SHELLY_IP)
    with patch("time.time", return_value=1733039773):
        power = pm.get_power()

    assert power.power == 20.00
    assert power.updated == 1733039773


def test_api_gen2_unavailable(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    """When all the fallback endpoints are not available, an exception should be raised."""
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 2}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Switch.GetStatus?id=0": ({}, 404),
            f"http://{DEFAULT_SHELLY_IP}/rpc/PM1.GetStatus?id=0": ({}, 404),
        },
    )

    with pytest.raises(ApiConnectionError):
        pm = ShellyPowerMeter(DEFAULT_SHELLY_IP)
        pm.get_power()


def test_connection_error_is_raised_on_request_exception() -> None:
    with patch("requests.get", side_effect=RequestException), pytest.raises(ApiConnectionError):
        pm = ShellyPowerMeter(DEFAULT_SHELLY_IP)
        pm.get_power()


def test_connection_error_is_raised_on_invalid_status_code(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({}, 500),
        },
    )

    with pytest.raises(ApiConnectionError):
        pm = ShellyPowerMeter(DEFAULT_SHELLY_IP)
        pm.get_power()
