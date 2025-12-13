"""Tests for the analytics module."""

from collections.abc import Generator
from datetime import timedelta
import json
from unittest.mock import patch

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.powercalc import CONF_CREATE_STANDBY_GROUP
from custom_components.powercalc.analytics.analytics import ENDPOINT_ANALYTICS, Analytics
from custom_components.powercalc.const import CONF_ENABLE_ANALYTICS, DOMAIN, DOMAIN_CONFIG, SensorType
from tests.common import get_simple_fixed_config, run_powercalc_setup

MOCK_PAYLOAD = {
    "test": "data",
}


@pytest.fixture
def payload_mock() -> Generator[None]:
    with patch(
        "custom_components.powercalc.analytics.analytics.Analytics._prepare_payload",
        return_value=MOCK_PAYLOAD,
    ):
        yield


@pytest.fixture(autouse=True)
def enable_analytics(hass: HomeAssistant) -> Generator[None]:
    hass.data[DOMAIN] = {DOMAIN_CONFIG: {CONF_ENABLE_ANALYTICS: True}}
    yield


@pytest.mark.asyncio
async def test_prepare_payload(hass: HomeAssistant) -> None:
    """Test the _prepare_payload method."""
    analytics = Analytics(hass)

    # Mock the get_count_by_sensor_type function
    mock_counts = {SensorType.VIRTUAL_POWER: 5, SensorType.GROUP: 2}

    # Since the function is called directly without await in _prepare_payload,
    # we need to mock it to return the value directly, not as a coroutine
    with (
        patch("custom_components.powercalc.analytics.analytics.get_count_by_sensor_type", return_value=mock_counts),
        patch("homeassistant.helpers.system_info.async_get_system_info", return_value={"installation_type": "Home Assistant OS"}),
    ):
        payload = await analytics._prepare_payload()

    # Verify the payload structure
    assert "install_id" in payload
    assert "ts" in payload
    assert "powercalc_version" in payload
    assert "ha_version" in payload
    assert "counts" in payload
    assert payload["counts"] == mock_counts
    assert "by_manufacturer" in payload
    assert "by_model" in payload

    assert json.dumps(payload)


async def test_send_analytics_success(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the send_analytics method with a successful response."""

    aioclient_mock.post(ENDPOINT_ANALYTICS, json={}, status=204)

    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("switch.test", 50),
        {
            CONF_ENABLE_ANALYTICS: True,
            CONF_CREATE_STANDBY_GROUP: False,
        },
    )

    async_fire_time_changed(
        hass,
        dt.utcnow() + timedelta(minutes=20),
    )
    await hass.async_block_till_done()

    assert len(aioclient_mock.mock_calls) == 1
    mock_call = aioclient_mock.mock_calls[0]
    posted_json = mock_call[2]
    assert posted_json["custom_profile_count"] > 50
    assert posted_json["counts"]["by_config_type"] == {"yaml": 1}
    assert posted_json["counts"]["by_sensor_type"] == {SensorType.VIRTUAL_POWER: 1}


@pytest.mark.usefixtures("payload_mock")
async def test_send_analytics_error_response(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the send_analytics method with an error response."""
    analytics = Analytics(hass)
    aioclient_mock.post(ENDPOINT_ANALYTICS, status=500)

    await analytics.send_analytics()

    assert aioclient_mock.call_count == 1
    assert f"Sending analytics failed with statuscode 500 from {ENDPOINT_ANALYTICS}" in caplog.text


@pytest.mark.usefixtures("payload_mock")
async def test_send_analytics_client_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the send_analytics method with a client error."""
    analytics = Analytics(hass)

    aioclient_mock.post(ENDPOINT_ANALYTICS, exc=aiohttp.ClientError("Test error"))

    await analytics.send_analytics()

    assert aioclient_mock.call_count == 1
    assert "Error sending analytics" in caplog.text


@pytest.mark.usefixtures("payload_mock")
async def test_send_analytics_timeout(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the send_analytics method with a timeout error."""
    analytics = Analytics(hass)

    aioclient_mock.post(ENDPOINT_ANALYTICS, exc=TimeoutError("Test timeout"))

    await analytics.send_analytics()

    assert aioclient_mock.call_count == 1
    assert "Timeout sending analytics" in caplog.text


@pytest.mark.usefixtures("payload_mock")
async def test_send_analytics_disabled(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test that analytics are not sent when analytics_enabled is False."""
    analytics = Analytics(hass)

    hass.data[DOMAIN] = {DOMAIN_CONFIG: {CONF_ENABLE_ANALYTICS: False}}

    await analytics.send_analytics()

    assert aioclient_mock.call_count == 0
