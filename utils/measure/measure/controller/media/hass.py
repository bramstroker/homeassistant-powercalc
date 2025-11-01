import logging

from homeassistant_api.errors import InternalServerError
import inquirer

from measure.const import QUESTION_ENTITY_ID
from measure.controller.hass_controller import HassControllerBase
from measure.controller.media.controller import MediaController

_LOGGER = logging.getLogger("measure")


class HassMediaController(HassControllerBase, MediaController):
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
                "Internal server error on media_player.turn_off service, probably because not supported by device, Trying media_player.media_stop",
            )
            self.client.trigger_service(
                "media_player",
                "media_stop",
                entity_id=self.entity_id,
            )

    def get_questions(self) -> list[inquirer.questions.Question]:
        return [
            inquirer.List(
                name=QUESTION_ENTITY_ID,
                message="Select the media player",
                choices=self.get_domain_entity_list("media_player"),
            ),
        ]
