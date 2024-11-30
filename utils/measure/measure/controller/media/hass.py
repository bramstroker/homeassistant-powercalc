import logging
from typing import Any

import inquirer
from homeassistant_api import Client
from homeassistant_api.errors import HomeassistantAPIError, InternalServerError

from measure.const import QUESTION_ENTITY_ID, QUESTION_MODEL_ID
from measure.controller.media.controller import MediaController
from measure.controller.media.errors import MediaPlayerError

_LOGGER = logging.getLogger("measure")


class HassMediaController(MediaController):
    def __init__(self, api_url: str, token: str) -> None:
        self._entity_id: str | None = None
        self._model_id: str | None = None
        try:
            self.client = Client(api_url, token, cache_session=False)
            self.client.get_config()
        except HomeassistantAPIError as e:
            raise MediaPlayerError(f"Failed to connect to HA API: {e}") from e

    def set_volume(self, volume: int) -> None:
        self.client.trigger_service(
            "media_player",
            "volume_set",
            entity_id=self._entity_id,
            volume_level=round(volume / 100, 2),
        )

    def mute_volume(self) -> None:
        self.client.trigger_service(
            "media_player",
            "mute_volume",
            entity_id=self._entity_id,
        )

    def play_audio(self, stream_url: str) -> None:
        self.client.trigger_service(
            "media_player",
            "play_media",
            entity_id=self._entity_id,
            media_content_type="music",
            media_content_id=stream_url,
        )

    def turn_off(self) -> None:
        try:
            self.client.trigger_service(
                "media_player",
                "turn_off",
                entity_id=self._entity_id,
            )
        except InternalServerError:
            _LOGGER.debug(
                "Internal server error on media_player.turn_off service, probably because not supported by device, Trying media_player.media_stop",
            )
            self.client.trigger_service(
                "media_player",
                "media_stop",
                entity_id=self._entity_id,
            )

    def get_questions(self) -> list[inquirer.questions.Question]:
        entities = self.client.get_entities()
        media_players = entities["media_player"].entities.values()
        entity_list = sorted([entity.entity_id for entity in media_players])

        return [
            inquirer.List(
                name=QUESTION_ENTITY_ID,
                message="Select the media player",
                choices=entity_list,
            ),
            inquirer.Text(
                name=QUESTION_MODEL_ID,
                message="What model is your media player? Ex: Sonos One SL",
                validate=lambda _, x: len(x) > 0,
            ),
        ]

    def process_answers(self, answers: dict[str, Any]) -> None:
        self._entity_id = answers[QUESTION_ENTITY_ID]
        self._model_id = answers[QUESTION_MODEL_ID]
