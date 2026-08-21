from unittest.mock import MagicMock

from measure.controller.media.hass import HassMediaController
from measure.home_assistant import HomeAssistantManager


def test_mute_volume_is_not_replayed_after_disconnect() -> None:
    client = _mock_client()

    _get_instance(client).mute_volume()

    client.trigger_service.assert_called_once_with(
        "media_player",
        "mute_volume",
        retry_on_disconnect=False,
        entity_id="media_player.test",
    )


def test_play_audio_is_not_replayed_after_disconnect() -> None:
    client = _mock_client()

    _get_instance(client).play_audio("https://example.com/audio.mp3")

    client.trigger_service.assert_called_once_with(
        "media_player",
        "play_media",
        retry_on_disconnect=False,
        entity_id="media_player.test",
        media_content_type="music",
        media_content_id="https://example.com/audio.mp3",
    )


def _get_instance(client: MagicMock) -> HassMediaController:
    return HassMediaController(client, entity_id="media_player.test")


def _mock_client() -> MagicMock:
    client = MagicMock(spec=HomeAssistantManager)
    client.get_config.return_value = {}
    return client
