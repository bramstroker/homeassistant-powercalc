from unittest.mock import patch

from measure.powermeter.errors import ApiConnectionError, UnsupportedFeatureError
from measure.powermeter.shelly import ShellyPowerMeter
import pytest
from requests import RequestException

from tests.conftest import MockRequestsGetFactory

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
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": ({"switch:0": {"apower": 20.00}}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Switch.GetStatus?id=0": ({"apower": 20.00}, 200),
        },
    )

    pm = ShellyPowerMeter(DEFAULT_SHELLY_IP)
    with patch("time.time", return_value=1733039773):
        power = pm.get_power()

    assert power.power == 20.00
    assert power.updated == 1733039773


def test_api_gen3_pm1_endpoint_with_voltage(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 3, "model": "S3PM-001PCEU16"}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": ({"pm1:0": {"apower": 20.00, "voltage": 230.1}}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/PM1.GetStatus?id=0": ({"apower": 20.00, "voltage": 230.1}, 200),
        },
    )

    pm = ShellyPowerMeter(DEFAULT_SHELLY_IP)
    with patch("time.time", return_value=1733039773):
        power = pm.get_power(include_voltage=True)

    assert power.power == 20.00
    assert power.voltage == 230.1
    assert power.updated == 1733039773
    assert pm.has_voltage_support() is True


def test_api_gen3_switch_endpoint(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 3, "model": "S3PL-00112EU"}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": ({"switch:1": {"apower": 7.5}}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Switch.GetStatus?id=1": ({"apower": 7.5}, 200),
        },
    )

    power_meter = ShellyPowerMeter(DEFAULT_SHELLY_IP)

    assert power_meter.get_power().power == 7.5
    assert power_meter.has_voltage_support() is False


def test_voltage_requires_numeric_voltage_in_component_status(
    mock_requests_get_factory: MockRequestsGetFactory,
) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 3}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": ({"switch:0": {"apower": 7.5}}, 200),
        },
    )

    power_meter = ShellyPowerMeter(DEFAULT_SHELLY_IP)

    with pytest.raises(UnsupportedFeatureError, match="Voltage measurement is not supported"):
        power_meter.get_power(include_voltage=True)


def test_api_gen2_unavailable(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 2}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": ({"wifi": {"sta_ip": DEFAULT_SHELLY_IP}}, 200),
        },
    )

    with pytest.raises(ApiConnectionError, match="No supported power measurement component"):
        ShellyPowerMeter(DEFAULT_SHELLY_IP)


def test_multiple_power_components_are_rejected(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 3}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": (
                {"switch:0": {"apower": 1.0}, "switch:1": {"apower": 2.0}},
                200,
            ),
        },
    )

    with pytest.raises(ApiConnectionError, match="Multiple power measurement components"):
        ShellyPowerMeter(DEFAULT_SHELLY_IP)


@pytest.mark.parametrize(
    "status_payload",
    (
        [],
        {"switch:invalid": {"apower": 1.0}},
        {"switch:0": {"apower": "1.0"}},
    ),
)
def test_invalid_rpc_status_is_rejected(
    mock_requests_get_factory: MockRequestsGetFactory,
    status_payload: object,
) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 3}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": (status_payload, 200),
        },
    )

    with pytest.raises(ApiConnectionError):
        ShellyPowerMeter(DEFAULT_SHELLY_IP)


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
