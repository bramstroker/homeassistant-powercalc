from unittest.mock import MagicMock, call, patch

from measure.powermeter.errors import ApiConnectionError, UnsupportedFeatureError
from measure.powermeter.shelly import ShellyPowerMeter
import pytest
from requests import RequestException
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from tests.conftest import MockRequestsGetFactory

DEFAULT_SHELLY_IP = "192.168.1.200"
SHELLY_ENDPOINT = f"http://{DEFAULT_SHELLY_IP}/shelly"


@pytest.mark.parametrize("info", [[], {"gen": True}, {"gen": None}, {"gen": "invalid"}, {"gen": 0}])
def test_invalid_device_information_is_rejected(
    mock_requests_get_factory: MockRequestsGetFactory,
    info: object,
) -> None:
    mock_requests_get_factory({SHELLY_ENDPOINT: (info, 200)})

    with pytest.raises(ApiConnectionError, match="invalid"):
        ShellyPowerMeter(DEFAULT_SHELLY_IP)


def test_invalid_json_is_reported_as_connection_error() -> None:
    response = MagicMock(status_code=200)
    response.json.side_effect = ValueError("Invalid JSON")

    with patch("requests.get", return_value=response), pytest.raises(ApiConnectionError, match="response was invalid"):
        ShellyPowerMeter(DEFAULT_SHELLY_IP)


@pytest.mark.parametrize(
    "reading,message",
    [
        ([], "response was invalid"),
        ({"meters": []}, "valid power value"),
        ({"meters": [{"power": True}]}, "valid power value"),
        ({"meters": [{"power": 1}]}, "valid timestamp"),
        ({"meters": [{"power": 1, "timestamp": "invalid"}]}, "valid timestamp"),
    ],
)
def test_gen1_rejects_malformed_reading_after_successful_probe(reading: object, message: str) -> None:
    responses = [
        MagicMock(status_code=200, json=lambda: {"gen": 1}),
        MagicMock(status_code=200, json=lambda: {"meters": [{"power": 1, "timestamp": 1234}]}),
        MagicMock(status_code=200, json=lambda: reading),
    ]
    with patch("requests.get", side_effect=responses):
        meter = ShellyPowerMeter(DEFAULT_SHELLY_IP)
        with pytest.raises(ApiConnectionError, match=message):
            meter.get_power()


@pytest.mark.parametrize(
    "reading,include_voltage,message",
    [
        ([], False, "valid power value"),
        ({"apower": None}, False, "valid power value"),
        ({"apower": float("nan")}, False, "valid power value"),
        ({"apower": True}, False, "valid power value"),
        ({"apower": 1}, True, "valid voltage value"),
        ({"apower": 1, "voltage": "230"}, True, "valid voltage value"),
        ({"apower": 1, "voltage": float("inf")}, True, "valid voltage value"),
    ],
)
def test_rpc_rejects_malformed_reading_after_successful_probe(
    reading: object,
    include_voltage: bool,
    message: str,
) -> None:
    responses = [
        MagicMock(status_code=200, json=lambda: {"gen": 3}),
        MagicMock(status_code=200, json=lambda: {"switch:0": {"apower": 1, "voltage": 230}}),
        MagicMock(status_code=200, json=lambda: reading),
    ]
    with patch("requests.get", side_effect=responses):
        meter = ShellyPowerMeter(DEFAULT_SHELLY_IP)
        with pytest.raises(ApiConnectionError, match=message):
            meter.get_power(include_voltage=include_voltage)


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


def test_api_gen1_uses_basic_authentication(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    requests_get = mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 1, "auth": True}, 200),
            f"http://{DEFAULT_SHELLY_IP}/status": ({"meters": [{"power": 20.0, "timestamp": 1733039773}]}, 200),
        },
    )

    power_meter = ShellyPowerMeter(DEFAULT_SHELLY_IP, username="measurement", password="secret")  # noqa: S106

    protected_call = requests_get.mock_calls[1]
    authentication = protected_call.kwargs["auth"]
    assert isinstance(authentication, HTTPBasicAuth)
    assert authentication.username == "measurement"
    assert authentication.password == "secret"  # noqa: S105
    assert power_meter.get_power().power == pytest.approx(20.0)


def test_api_gen2_uses_digest_authentication(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    requests_get = mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 2, "auth_en": True}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": ({"switch:0": {"apower": 20.0}}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Switch.GetStatus?id=0": ({"apower": 20.0}, 200),
        },
    )

    power_meter = ShellyPowerMeter(DEFAULT_SHELLY_IP, username="ignored", password="secret")  # noqa: S106

    authentication = requests_get.mock_calls[1].kwargs["auth"]
    assert isinstance(authentication, HTTPDigestAuth)
    assert authentication.username == "admin"
    assert authentication.password == "secret"  # noqa: S105
    assert power_meter.get_power().power == pytest.approx(20.0)


def test_api_rejects_incorrect_credentials(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 2, "auth_en": True}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": ({}, 401),
        },
    )

    with pytest.raises(ApiConnectionError, match="username or password is incorrect"):
        ShellyPowerMeter(DEFAULT_SHELLY_IP, password="incorrect")  # noqa: S106


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

    assert power.power == pytest.approx(20.00)
    assert power.voltage == pytest.approx(230.1)
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

    assert power_meter.get_power().power == pytest.approx(7.5)
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


@pytest.mark.parametrize("component_key", ["unknown:0", "meter:0", "switch:not-a-number", "switch"])
@pytest.mark.parametrize("has_supported_component", [False, True])
def test_rpc_ignores_unsupported_components(
    mock_requests_get_factory: MockRequestsGetFactory, component_key: str, has_supported_component: bool
) -> None:
    status = {component_key: {"apower": 2.0}}
    if has_supported_component:
        status["switch:1"] = {"apower": 3.0}
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({"gen": 3}, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Shelly.GetStatus": (status, 200),
            f"http://{DEFAULT_SHELLY_IP}/rpc/Switch.GetStatus?id=1": ({"apower": 3.0}, 200),
        }
    )

    if has_supported_component:
        meter = ShellyPowerMeter(DEFAULT_SHELLY_IP)
        assert meter.get_power().power == 3.0
    else:
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
    [
        [],
        {"switch:invalid": {"apower": 1.0}},
        {"switch:0": {"apower": "1.0"}},
    ],
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
        ShellyPowerMeter(DEFAULT_SHELLY_IP)


def test_connection_error_is_raised_on_invalid_status_code(mock_requests_get_factory: MockRequestsGetFactory) -> None:
    mock_requests_get_factory(
        {
            SHELLY_ENDPOINT: ({}, 500),
        },
    )

    with pytest.raises(ApiConnectionError):
        ShellyPowerMeter(DEFAULT_SHELLY_IP)


def test_rate_limited_request_is_retried() -> None:
    responses = [
        MagicMock(status_code=200, json=lambda: {"gen": 3}),
        MagicMock(status_code=429),
        MagicMock(status_code=200, json=lambda: {"switch:0": {"apower": 20.0}}),
    ]

    with patch("requests.get", side_effect=responses) as requests_get, patch("time.sleep") as sleep:
        ShellyPowerMeter(DEFAULT_SHELLY_IP)

    assert requests_get.call_count == 3
    assert sleep.mock_calls == [call(2)]


def test_rate_limited_request_fails_after_one_retry() -> None:
    responses = [
        MagicMock(status_code=200, json=lambda: {"gen": 3}),
        MagicMock(status_code=429),
        MagicMock(status_code=429),
    ]

    with (
        patch("requests.get", side_effect=responses) as requests_get,
        patch("time.sleep") as sleep,
        pytest.raises(ApiConnectionError, match="RPC status endpoint returned HTTP 429"),
    ):
        ShellyPowerMeter(DEFAULT_SHELLY_IP)

    assert requests_get.call_count == 3
    assert sleep.mock_calls == [call(2)]
