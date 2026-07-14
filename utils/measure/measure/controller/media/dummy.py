from measure.controller.media.controller import MediaController


class DummyMediaController(MediaController):
    def set_volume(self, volume: int) -> None:
        # Dummy controller intentionally performs no media device action.
        pass

    def mute_volume(self) -> None:
        # Dummy controller intentionally performs no media device action.
        pass

    def play_audio(self, stream_url: str) -> None:
        # Dummy controller intentionally performs no media device action.
        pass

    def turn_off(self) -> None:
        # Dummy controller intentionally performs no media device action.
        pass
