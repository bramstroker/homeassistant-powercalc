"""Expose the same test helpers with either Home Assistant test plugin."""

from importlib.util import find_spec

USING_OFFICIAL_PLUGIN = find_spec("pytest_homeassistant") is not None

if USING_OFFICIAL_PLUGIN:
    from pytest_homeassistant.common import (
        MockConfigEntry,
        MockEntity,
        MockToggleEntity,
        RegistryEntryWithDefaults,
        async_fire_time_changed,
        mock_device_registry,
        mock_registry,
        mock_restore_cache,
        mock_restore_cache_with_extra_data,
        setup_test_component_platform,
    )
    from pytest_homeassistant.components.recorder.common import (
        async_wait_purge_done,
        async_wait_recording_done,
        do_adhoc_statistics,
        get_start_time,
        statistics_during_period,
    )
    from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker
else:
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        MockEntity,
        MockToggleEntity,
        RegistryEntryWithDefaults,
        async_fire_time_changed,
        mock_device_registry,
        mock_registry,
        mock_restore_cache,
        mock_restore_cache_with_extra_data,
        setup_test_component_platform,
    )
    from pytest_homeassistant_custom_component.components.recorder.common import (
        async_wait_purge_done,
        async_wait_recording_done,
        do_adhoc_statistics,
        get_start_time,
        statistics_during_period,
    )
    from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

__all__ = [
    "USING_OFFICIAL_PLUGIN",
    "AiohttpClientMocker",
    "MockConfigEntry",
    "MockEntity",
    "MockToggleEntity",
    "RegistryEntryWithDefaults",
    "async_fire_time_changed",
    "async_wait_purge_done",
    "async_wait_recording_done",
    "do_adhoc_statistics",
    "get_start_time",
    "mock_device_registry",
    "mock_registry",
    "mock_restore_cache",
    "mock_restore_cache_with_extra_data",
    "setup_test_component_platform",
    "statistics_during_period",
]
