#!/usr/bin/env python3
"""
Generate a markdown supporters section for Release Drafter,
using Buy Me a Coffee's supporters + subscriptions APIs.

Requires:
- Python 3.13+
- `requests` installed
- Environment variables:
    - BMC_API_TOKEN
    - BMC_SLUG
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from typing import Any

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests


BMC_SUPPORTERS_URL = "https://developers.buymeacoffee.com/api/v1/supporters"
BMC_SUBSCRIPTIONS_URL = "https://developers.buymeacoffee.com/api/v1/subscriptions"

# Beer tiers: exact coffees count → label
TIERS: list[dict[str, Any]] = [
    {"coffees": 5, "label": "🏆 5 coffees"},
    {"coffees": 3, "label": "🥈 3 coffees"},
    {"coffees": 2, "label": "🥉 2 coffees"},
    {"coffees": 1, "label": "⭐ 1 coffee"},
]

# Display limits
MAX_NAMES_PER_TIER = 3
MAX_MONTHLY_NAMES = 5

# Safety cap for pagination; very generous for typical BMC usage
DEFAULT_MAX_PAGES = 50


# ---------- HTTP / pagination helpers ----------

def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def _with_page(url: str, page: int) -> str:
    """
    Add or replace the `page` query parameter in `url`.
    Handles URLs that may already have other query params (like status=active).
    """
    split = urlsplit(url)
    query_pairs = dict(parse_qsl(split.query, keep_blank_values=True))
    query_pairs["page"] = str(page)
    new_query = urlencode(query_pairs)
    return urlunsplit(
        (
            split.scheme,
            split.netloc,
            split.path,
            new_query,
            split.fragment,
        )
    )


def _paginated_get(
    url: str,
    token: str,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """
    Generic pagination helper for BMC's Laravel-style responses.

    Expects a response like:
    {
      "current_page": 1,
      "data": [...],
      "last_page": 2,
      "next_page_url": "...",
      ...
    }
    """
    headers = _auth_headers(token)
    all_items: list[dict[str, Any]] = []

    hard_max_pages = max_pages or DEFAULT_MAX_PAGES
    page = 1

    while page <= hard_max_pages:
        page_url = _with_page(url, page)
        resp = requests.get(page_url, headers=headers, timeout=10)
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()

        data = payload.get("data") or []
        if not isinstance(data, list):
            break

        all_items.extend(data)

        current_page = int(payload.get("current_page") or page)
        last_page = int(payload.get("last_page") or current_page)
        next_page_url = payload.get("next_page_url")

        if not next_page_url or current_page >= last_page:
            break

        page += 1

    return all_items


# ---------- BMC data fetchers ----------

def fetch_supporters(
    token: str,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch supporters from Buy Me a Coffee across pages.

    Returns only *public* supporters (support_visibility == 1).
    """
    raw_items = _paginated_get(BMC_SUPPORTERS_URL, token, max_pages=max_pages)

    supporters: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if item.get("support_visibility") != 1:
            continue
        supporters.append(item)

    return supporters


def fetch_active_subscriptions(
    token: str,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch active subscriptions (memberships) from Buy Me a Coffee,
    across pages.

    Endpoint: /api/v1/subscriptions?status=active
    """
    base_url = f"{BMC_SUBSCRIPTIONS_URL}?status=active"
    items = _paginated_get(base_url, token, max_pages=max_pages)

    # We don't filter visibility here; subscriptions are typically
    # already based on members who've opted in.
    return [item for item in items if isinstance(item, dict)]


# ---------- name / grouping helpers ----------

def name_from_supporter(item: dict[str, Any]) -> str:
    """
    Get a display name for a one-off supporter.
    """
    return (
        str(item.get("supporter_name") or "").strip()
        or str(item.get("payer_name") or "").strip()
        or "Anonymous legend"
    )


def name_from_subscription(item: dict[str, Any]) -> str:
    """
    Get a display name for a monthly supporter.
    """
    return (
        str(item.get("supporter_name") or "").strip()
        or str(item.get("payer_name") or "").strip()
        or str(item.get("member_name") or "").strip()
        or "Anonymous monthly legend"
    )


def group_supporters_by_tier(
    supporters: list[dict[str, Any]],
    max_names_per_tier: int = MAX_NAMES_PER_TIER,
) -> dict[str, dict[str, Any]]:
    """
    Group supporters into beer tiers.

    Returns:
        {
          "🏆 5 beers": {"names": [str, ...], "more": bool},
          "🥈 3 beers": {...},
          ...
        }
    """
    by_coffees: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for s in supporters:
        coffees_raw = s.get("support_coffees", 0)
        try:
            coffees = int(coffees_raw)
        except (TypeError, ValueError):
            continue
        if coffees <= 0:
            continue

        by_coffees[coffees].append(s)

    tiered: dict[str, dict[str, Any]] = {}

    for tier in TIERS:
        coffees_value = int(tier["coffees"])
        label = str(tier["label"])

        matches = by_coffees.get(coffees_value, [])
        if not matches:
            continue

        # BMC returns most recent first, so slicing keeps that order
        names = [name_from_supporter(item) for item in matches[:max_names_per_tier]]
        more = len(matches) > max_names_per_tier

        tiered[label] = {"names": names, "more": more}

    return tiered


def build_monthly_supporters_block(
    subs: list[dict[str, Any]],
    max_names: int = MAX_MONTHLY_NAMES,
) -> list[str]:
    """
    Build the markdown lines for the monthly supporters tier.
    """
    if not subs:
        return []

    names: list[str] = []
    for item in subs:
        names.append(name_from_subscription(item))
        if len(names) >= max_names:
            break

    more = len(subs) > max_names

    lines: list[str] = ["💝 Monthly supporters"]
    lines.extend(names)
    if more:
        lines.append("and other legends")

    return lines


# ---------- main assembly ----------

def build_supporters_section(token: str, slug: str) -> str:
    """
    Build the final markdown section.

    Example shape:

    Supporters powering this project ⚡ 👇

    💝 Monthly supporters
    Alice
    Bob
    and other legends

    🏆 5 beers
    Kenneth
    Someone
    exi
    and other legends

    ...
    """
    # Walk pages to get a complete view, so you can actually fill
    # at least ~3 names per tier if they exist at all.
    supporters = fetch_supporters(token)
    subs = fetch_active_subscriptions(token)

    if not supporters and not subs:
        return (
            "Supporters powering this project ⚡ 👇\n\n"
            "_No public supporters found yet._\n"
            f"Support the project at https://buymeacoffee.com/{slug}"
        )

    tiered = group_supporters_by_tier(supporters)

    lines: list[str] = []
    lines.append("## Supporters powering this project ⚡ 👇")
    lines.append("")

    # Monthly supporters first
    monthly_lines = build_monthly_supporters_block(subs)
    if monthly_lines:
        lines.extend(monthly_lines)
        lines.append("")

    # Beer tiers in defined order
    for tier in TIERS:
        label = str(tier["label"])
        block = tiered.get(label)
        if not block:
            continue

        names = block["names"]
        more = bool(block["more"])

        lines.append(label)
        lines.extend(str(n) for n in names)
        if more:
            lines.append("and other legends")
        lines.append("")

    lines.append("")
    lines.append(f"Support the project at https://buymeacoffee.com/{slug}")

    while len(lines) >= 2 and not lines[-2].strip():
        lines.pop(-2)

    return "\n".join(lines)


def main() -> int:
    token = os.getenv("BMC_API_TOKEN")
    slug = os.getenv("BMC_SLUG")

    if not token:
        print("BMC_API_TOKEN is not set", file=sys.stderr)
        return 1
    if not slug:
        print("BMC_SLUG is not set", file=sys.stderr)
        return 1

    section = build_supporters_section(token=token, slug=slug)
    print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
