from collections.abc import Callable
from typing import cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest

from custom_components.powercalc.const import DOMAIN
from custom_components.powercalc.issues import async_create_config_entry_issue
from tests.common import create_mock_config_entry


@pytest.mark.parametrize("supports_ownership", [True, False], ids=["owned_issues", "legacy_api"])
async def test_create_config_entry_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    monkeypatch: pytest.MonkeyPatch,
    supports_ownership: bool,
) -> None:
    """Use ownership only when supported, while preserving the repair flow metadata."""
    entry = await create_mock_config_entry(hass, {}, setup=False)
    original_create_issue = cast(Callable[..., None], ir.async_create_issue)
    owners: list[str | None] = []

    def create_owned_issue(
        hass: HomeAssistant,
        domain: str,
        issue_id: str,
        *,
        config_entry_id: str | None = None,
        **kwargs: object,
    ) -> None:
        owners.append(config_entry_id)
        original_create_issue(hass, domain, issue_id, **kwargs)

    def create_legacy_issue(hass: HomeAssistant, domain: str, issue_id: str, **kwargs: object) -> None:
        assert "config_entry_id" not in kwargs
        create_owned_issue(hass, domain, issue_id, **kwargs)

    monkeypatch.setattr(ir, "async_create_issue", create_owned_issue if supports_ownership else create_legacy_issue)

    async_create_config_entry_issue(
        hass,
        entry,
        "test_issue",
        translation_key="sub_profile",
        translation_placeholders={"entry": entry.title},
    )

    assert owners == [entry.entry_id if supports_ownership else None]
    issue = issue_registry.async_get_issue(DOMAIN, "test_issue")
    assert issue
    assert issue.data == {"config_entry_id": entry.entry_id}
    assert issue.is_fixable
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_key == "sub_profile"
    assert issue.translation_placeholders == {"entry": entry.title}
