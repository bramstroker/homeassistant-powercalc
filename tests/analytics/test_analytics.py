"""Tests for the analytics module."""

from collections.abc import Generator
from datetime import timedelta
from unittest.mock import patch

import aiohttp
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.util import dt
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.powercalc import CONF_CREATE_STANDBY_GROUP, CONF_SENSOR_TYPE
from custom_components.powercalc.analytics.analytics import ENDPOINT_ANALYTICS, Analytics
from custom_components.powercalc.const import (
    CONF_ENABLE_ANALYTICS,
    CONF_MANUFACTURER,
    CONF_MODEL,
    DOMAIN,
    DOMAIN_CONFIG,
    SERVICE_RELOAD,
    CalculationStrategy,
    SensorType,
)
from tests.common import get_simple_fixed_config, run_powercalc_setup, setup_config_entry

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


async def test_send_analytics_success(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the send_analytics method with a successful response."""

    aioclient_mock.post(ENDPOINT_ANALYTICS, json={}, status=204)

    await run_powercalc_setup(
        hass,
        [
            get_simple_fixed_config("switch.test", 50),
            {
                CONF_ENTITY_ID: "light.test",
                CONF_MANUFACTURER: "signify",
                CONF_MODEL: "LCT010",
            },
        ],
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
    assert posted_json["counts"]["by_config_type"] == {"yaml": 2}
    assert posted_json["counts"]["by_sensor_type"] == {SensorType.VIRTUAL_POWER: 2}
    assert posted_json["counts"]["by_manufacturer"] == {"signify": 1}
    assert posted_json["counts"]["by_model"] == {"signify:LCT010": 1}
    assert posted_json["counts"]["by_strategy"] == {CalculationStrategy.FIXED: 1, CalculationStrategy.LUT: 1}


@pytest.mark.usefixtures("payload_mock")
async def test_install_id_is_stored(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(ENDPOINT_ANALYTICS, json={}, status=204)

    analytics = Analytics(hass)
    await analytics.load()

    # Sending analytics without an install_id known should generate a new uuid
    await analytics.send_analytics()
    install_id = analytics.install_id

    # Create fresh analytics instance. install_id should be used from store powercalc.analytics
    analytics = Analytics(hass)
    await analytics.load()
    assert install_id == analytics.install_id


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


async def test_no_duplicate_count_after_entry_reload(hass: HomeAssistant) -> None:
    entry = await setup_config_entry(
        hass,
        {
            CONF_SENSOR_TYPE: SensorType.VIRTUAL_POWER,
            CONF_ENTITY_ID: "light.test",
            CONF_MANUFACTURER: "test",
            CONF_MODEL: "lut_white",
        },
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)

    analytics = Analytics(hass)
    payload = await analytics._prepare_payload()  # noqa: SLF001

    assert payload["counts"]["by_config_type"] == {"gui": 1}
    assert payload["counts"]["by_manufacturer"] == {"test": 1}


async def test_no_duplicate_count_after_config_reload(hass: HomeAssistant) -> None:
    await run_powercalc_setup(
        hass,
        get_simple_fixed_config("switch.test", 50),
        {CONF_CREATE_STANDBY_GROUP: False},
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_RELOAD,
        blocking=True,
    )
    await hass.async_block_till_done()

    analytics = Analytics(hass)
    payload = await analytics._prepare_payload()  # noqa: SLF001

    assert payload["counts"]["by_config_type"] == {"yaml": 1}
