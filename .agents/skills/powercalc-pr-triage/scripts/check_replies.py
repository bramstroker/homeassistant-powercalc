#!/usr/bin/env python3
"""Report comments after the user's latest comment on labeled open GitHub PRs."""

# ruff: noqa: T201 -- This command writes JSON to stdout and progress/errors to stderr.

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import subprocess
import sys
from urllib.parse import quote, urlencode


def read_api(endpoint: str, *, paginate: bool = False) -> object:
    command = ["gh", "api", "--method", "GET", endpoint]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    result = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603 -- Fixed gh command; no shell.
    data = json.loads(result.stdout)
    if paginate:
        return [item for page in data for item in page]
    return data


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def collect_comments(repo: str, number: int) -> list[dict]:
    sources = [
        ["discussion", f"repos/{repo}/issues/{number}/comments", "created_at"],
        ["inline_review", f"repos/{repo}/pulls/{number}/comments", "created_at"],
        ["review", f"repos/{repo}/pulls/{number}/reviews", "submitted_at"],
    ]
    comments = []
    for kind, endpoint, time_field in sources:
        for item in read_api(f"{endpoint}?per_page=100", paginate=True):
            body = item.get("body") or ""
            timestamp = item.get(time_field)
            if not body.strip() or not timestamp:
                continue
            author = item.get("user") or {}
            login = author.get("login") or "[deleted]"
            comments.append(
                {
                    "kind": kind,
                    "author": login,
                    "is_bot": author.get("type") == "Bot" or login.endswith("[bot]"),
                    "created_at": timestamp,
                    "url": item["html_url"],
                    "body": body,
                }
            )
    comments.sort(key=lambda comment: parse_time(comment["created_at"]))
    return comments


def summarize_pr(pr: dict, comments: list[dict], login: str) -> dict:
    own_comments = [comment for comment in comments if comment["author"].casefold() == login.casefold()]
    latest_own = own_comments[-1] if own_comments else None
    new_comments = []
    if latest_own:
        cutoff = parse_time(latest_own["created_at"])
        new_comments = [
            comment
            for comment in comments
            if comment["author"].casefold() != login.casefold() and parse_time(comment["created_at"]) > cutoff
        ]
    if latest_own is None:
        status = "no_baseline"
    elif any(not comment["is_bot"] for comment in new_comments):
        status = "new_human_comments"
    elif new_comments:
        status = "bot_only"
    else:
        status = "no_new_comments"
    return {
        "number": pr["number"],
        "title": pr["title"],
        "url": pr["html_url"],
        "author": (pr.get("user") or {}).get("login"),
        "status": status,
        "latest_user_comment": latest_own,
        "new_comments": new_comments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="bramstroker/homeassistant-powercalc")
    parser.add_argument("--label", default="waiting-for-author")
    parser.add_argument("--login")
    args = parser.parse_args()
    login = args.login or read_api("user")["login"]
    # Verify the exact label so a typo cannot silently produce an empty report.
    read_api(f"repos/{args.repo}/labels/{quote(args.label, safe='')}")
    query = urlencode({"state": "open", "labels": args.label, "per_page": 100})
    issues = read_api(f"repos/{args.repo}/issues?{query}", paginate=True)
    prs = [issue for issue in issues if "pull_request" in issue]
    reports = []
    for pr in prs:
        print(f"Checking #{pr['number']}: {pr['title']}", file=sys.stderr)
        comments = collect_comments(args.repo, pr["number"])
        reports.append(summarize_pr(pr, comments, login))
    counts = {}
    for report in reports:
        status = report["status"]
        counts[status] = counts.get(status, 0) + 1
    print(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "repository": args.repo,
                "label": args.label,
                "login": login,
                "total_prs": len(reports),
                "counts": counts,
                "pull_requests": reports,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(error.stderr or str(error), file=sys.stderr)
        raise SystemExit(error.returncode) from error
