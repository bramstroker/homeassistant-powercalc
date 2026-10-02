"""Expose the validation engine used by the running Home Assistant version."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # HA 2026.10 aliases voluptuous to probatio at startup. Type checkers cannot
    # see that alias, while older HA releases still need voluptuous at runtime.
    import probatio as vol
else:
    import voluptuous as vol

__all__ = ["vol"]
