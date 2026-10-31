"""Create repair issues across supported Home Assistant versions."""

from collections.abc import Callable
import inspect
from typing import cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN


@callback
def async_create_config_entry_issue(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    issue_id: str,
    *,
    translation_key: str,
    translation_placeholders: dict[str, str],
) -> None:
    """Create a fixable warning, linked to its config entry when HA supports it."""
    ownership: dict[str, str] = {}
    if "config_entry_id" in inspect.signature(ir.async_create_issue).parameters:
        ownership["config_entry_id"] = config_entry.entry_id

    # Older HA type hints do not include the optional ownership argument.
    create_issue = cast(Callable[..., None], ir.async_create_issue)
    create_issue(
        hass,
        DOMAIN,
        issue_id,
        data={"config_entry_id": config_entry.entry_id},
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=translation_key,
        translation_placeholders=translation_placeholders,
        **ownership,
    )
