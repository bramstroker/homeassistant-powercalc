#!/usr/bin/env python3
"""
Generate a markdown supporters section for Release Drafter,
using Buy Me a Coffee's supporters + subscriptions APIs.

Requires:
- Python 3.13+
- `requests` installed
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import requests

SUPPORTERS_API = "https://api.powercalc.nl/supporters/one-time"
SUBSCRIPTIONS_API = "https://api.powercalc.nl/supporters/subscriptions"

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


# ---------- HTTP / pagination helpers ----------

def _get(url: str) -> list[dict[str, Any]]:
    """
    Simple GET request helper.
    """
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data: list[dict] = resp.json()
    if not isinstance(data, list):
        return []

    return data

# ---------- Data fetchers ----------

def fetch_supporters(
) -> list[dict[str, Any]]:
    """
    Fetch supporters from Buy Me a Coffee across pages.

    Returns only *public* supporters (support_visibility == 1).
    """
    return [s for s in _get(SUPPORTERS_API) if s.get("name") != "Someone"]


def fetch_active_subscriptions(
) -> list[dict[str, Any]]:
    """
    Fetch active subscriptions (memberships)
    """
    base_url = f"{SUBSCRIPTIONS_API}"
    items = _get(base_url)

    return [item for item in items if item.get("status") == "active"]


# ---------- grouping helpers ----------

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
        coffees_raw = s.get("coffees", 0)
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
        names = [item.get("name") for item in matches[:max_names_per_tier]]
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
        names.append(item.get("name"))
        if len(names) >= max_names:
            break

    more = len(subs) > max_names

    lines: list[str] = ["💝 Monthly supporters"]
    lines.extend(names)
    if more:
        lines.append("and other legends")

    return lines


# ---------- main assembly ----------

def build_supporters_section() -> str:
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
    supporters = fetch_supporters()
    subs = fetch_active_subscriptions()

    if not supporters and not subs:
        return (
            "Supporters powering this project ⚡ 👇\n\n"
            "_No public supporters found yet._\n"
            f"Support the project at https://buymeacoffee.com/bramski"
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
    lines.append(f"Support the project at https://buymeacoffee.com/bramski")

    return "\n".join(lines)


def main() -> int:
    section = build_supporters_section()
    print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
