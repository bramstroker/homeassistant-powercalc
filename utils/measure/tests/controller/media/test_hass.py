from unittest.mock import MagicMock, call

from homeassistant_api.errors import InternalServerError, WebsocketError
from measure.controller.media.hass import HassMediaController
import pytest


@pytest.mark.parametrize("volume,expected", [(0, 0.0), (1, 0.01), (35, 0.35), (100, 1.0)])
def test_set_volume_converts_percentage_to_home_assistant_level(
    hass_client: MagicMock, volume: int, expected: float
) -> None:
    _get_instance(hass_client).set_volume(volume)

    hass_client.trigger_service.assert_called_once_with(
        "media_player",
        "volume_set",
        entity_id="media_player.test",
        volume_level=expected,
    )


def test_turn_off_uses_device_power_service(hass_client: MagicMock) -> None:
    _get_instance(hass_client).turn_off()

    hass_client.trigger_service.assert_called_once_with("media_player", "turn_off", entity_id="media_player.test")


def test_turn_off_stops_playback_when_power_service_is_unsupported(hass_client: MagicMock) -> None:
    hass_client.trigger_service.side_effect = [InternalServerError(500, "Not supported"), None]

    _get_instance(hass_client).turn_off()

    assert hass_client.trigger_service.call_args_list == [
        call("media_player", "turn_off", entity_id="media_player.test"),
        call("media_player", "media_stop", entity_id="media_player.test"),
    ]


def test_turn_off_propagates_connection_failure_without_fallback(hass_client: MagicMock) -> None:
    hass_client.trigger_service.side_effect = WebsocketError("Disconnected")

    with pytest.raises(WebsocketError, match="Disconnected"):
        _get_instance(hass_client).turn_off()

    hass_client.trigger_service.assert_called_once_with("media_player", "turn_off", entity_id="media_player.test")


def test_turn_off_propagates_stop_playback_failure(hass_client: MagicMock) -> None:
    hass_client.trigger_service.side_effect = [
        InternalServerError(500, "Not supported"),
        InternalServerError(500, "Cannot stop"),
    ]

    with pytest.raises(InternalServerError, match="Cannot stop"):
        _get_instance(hass_client).turn_off()

    assert hass_client.trigger_service.call_args_list == [
        call("media_player", "turn_off", entity_id="media_player.test"),
        call("media_player", "media_stop", entity_id="media_player.test"),
    ]


def test_mute_volume_is_not_replayed_after_disconnect(hass_client: MagicMock) -> None:
    _get_instance(hass_client).mute_volume()

    hass_client.trigger_service.assert_called_once_with(
        "media_player",
        "volume_mute",
        retry_on_disconnect=False,
        entity_id="media_player.test",
        is_volume_muted=True,
    )


def test_play_audio_is_not_replayed_after_disconnect(hass_client: MagicMock) -> None:
    _get_instance(hass_client).play_audio("https://example.com/audio.mp3")

    hass_client.trigger_service.assert_called_once_with(
        "media_player",
        "play_media",
        retry_on_disconnect=False,
        entity_id="media_player.test",
        media_content_type="music",
        media_content_id="https://example.com/audio.mp3",
    )


def _get_instance(client: MagicMock) -> HassMediaController:
    return HassMediaController(client, entity_id="media_player.test")
