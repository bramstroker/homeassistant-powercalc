import logging

from measure import config
from measure.config import MeasureConfig
from measure.controller.media.const import MediaControllerType
from measure.controller.media.controller import MediaController
from measure.controller.media.dummy import DummyMediaController
from measure.controller.media.hass import HassMediaController

_LOGGER = logging.getLogger("measure")


class MediaControllerFactory:
    @staticmethod
    def hass(config: MeasureConfig) -> HassMediaController:
        return HassMediaController(config.hass_url, config.hass_token)

    @staticmethod
    def dummy(config: MeasureConfig) -> DummyMediaController:
        return DummyMediaController()

    def create(self, config: MeasureConfig) -> MediaController:
        """Create the media controller instance"""
        factories = {
            MediaControllerType.DUMMY: self.dummy,
            MediaControllerType.HASS: self.hass,
        }
        factory = factories.get(config.selected_media_controller)
        if factory is None:
            raise Exception(
                f"Could not find a factory for {config.selected_media_controller}",
            )

        return factory(config)
