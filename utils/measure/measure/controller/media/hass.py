import logging

from homeassistant_api.errors import InternalServerError

from measure.controller.hass_controller import HassControllerBase
from measure.controller.media.controller import MediaController
from measure.home_assistant import HomeAssistantManager

_LOGGER = logging.getLogger("measure")


class HassMediaController(HassControllerBase, MediaController):
    def __init__(
        self,
        home_assistant: HomeAssistantManager,
        *,
        entity_id: str | None = None,
    ) -> None:
        super().__init__(home_assistant, entity_id=entity_id)

    def set_volume(self, volume: int) -> None:
        self.client.trigger_service(
            "media_player",
            "volume_set",
            entity_id=self.entity_id,
            volume_level=round(volume / 100, 2),
        )

    def mute_volume(self) -> None:
        self.client.trigger_service(
            "media_player",
            "mute_volume",
            entity_id=self.entity_id,
        )

    def play_audio(self, stream_url: str) -> None:
        self.client.trigger_service(
            "media_player",
            "play_media",
            entity_id=self.entity_id,
            media_content_type="music",
            media_content_id=stream_url,
        )

    def turn_off(self) -> None:
        try:
            self.client.trigger_service(
                "media_player",
                "turn_off",
                entity_id=self.entity_id,
            )
        except InternalServerError:
            _LOGGER.debug(
                "Internal server error on media_player.turn_off service, probably because not "
                "supported by device, Trying media_player.media_stop",
            )
            self.client.trigger_service(
                "media_player",
                "media_stop",
                entity_id=self.entity_id,
            )
