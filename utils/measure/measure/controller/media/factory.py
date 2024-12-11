import logging

from measure.config import MeasureConfig
from measure.controller.media.const import MediaControllerType
from measure.controller.media.controller import MediaController
from measure.controller.media.dummy import DummyMediaController
from measure.controller.media.hass import HassMediaController

_LOGGER = logging.getLogger("measure")


class MediaControllerFactory:
    def __init__(self, config: MeasureConfig) -> None:
        self.config = config

    def hass(self) -> HassMediaController:
        return HassMediaController(self.config.hass_url, self.config.hass_token)

    @staticmethod
    def dummy() -> DummyMediaController:
        return DummyMediaController()

    def create(self) -> MediaController:
        """Create the media controller instance"""
        factories = {
            MediaControllerType.DUMMY: self.dummy,
            MediaControllerType.HASS: self.hass,
        }
        factory = factories.get(self.config.selected_media_controller)
        if factory is None:
            raise Exception(
                f"Could not find a factory for {self.config.selected_media_controller}",
            )

        return factory()
