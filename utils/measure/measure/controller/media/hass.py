import logging

from homeassistant_api.errors import InternalServerError, ResponseError

from measure.controller.hass_controller import HassControllerBase
from measure.controller.media.controller import MediaController
from measure.home_assistant.client import HomeAssistantManager

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
            "volume_mute",
            retry_on_disconnect=False,
            entity_id=self.entity_id,
            is_volume_muted=True,
        )

    def unmute_volume(self) -> None:
        self.client.trigger_service(
            "media_player",
            "volume_mute",
            retry_on_disconnect=False,
            entity_id=self.entity_id,
            is_volume_muted=False,
        )

    def play_audio(self, stream_url: str) -> None:
        self.client.trigger_service(
            "media_player",
            "play_media",
            retry_on_disconnect=False,
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
        except (InternalServerError, ResponseError) as error:
            # The WebSocket API reports unsupported actions as validation errors.
            # Other response errors must still fail the measurement.
            if isinstance(error, ResponseError) and not (
                str(error).startswith("[service_validation_error]")
                and "does not support action media_player.turn_off" in str(error)
            ):
                raise
            _LOGGER.debug(
                "Could not turn off speaker (%s), trying media_player.media_stop",
                error,
            )
            self.client.trigger_service(
                "media_player",
                "media_stop",
                entity_id=self.entity_id,
            )
