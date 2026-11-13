#!/usr/bin/env python3
"""Find incoming and follow-up work in open GitHub PRs, issues, and discussions."""

# ruff: noqa: T201 -- This command writes JSON to stdout and progress/errors to stderr.

from __future__ import annotations

import argparse
from collections.abc import Iterator
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlencode

DISCUSSIONS_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    discussions(first: 100, after: $cursor, states: [OPEN], orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        id number title url body createdAt isAnswered
        author { login __typename }
        category { name }
        labels(first: 100) { nodes { name } pageInfo { hasNextPage } }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

DISCUSSION_COMMENTS_QUERY = """
query($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on Discussion {
      comments(first: 100, after: $cursor) {
        nodes {
          id body createdAt url author { login __typename }
          replies(first: 100) {
            nodes { id body createdAt url author { login __typename } }
            pageInfo { hasNextPage endCursor }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

DISCUSSION_REPLIES_QUERY = """
query($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on DiscussionComment {
      replies(first: 100, after: $cursor) {
        nodes { id body createdAt url author { login __typename } }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

ATTENTION_STATUSES = {
    "new_incoming",
    "no_baseline",
    "new_human_comments",
    "new_commits",
    "new_human_comments_and_commits",
}

DEFAULT_STATE_PATH = Path(__file__).resolve().parents[4] / ".powercalc-triage" / "state.json"


def read_state(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "acknowledgments": {}}
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Cannot read triage state at {path}: {error}") from error
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("acknowledgments"), dict):
        raise RuntimeError(f"Invalid triage state at {path}")
    acknowledgments = state["acknowledgments"]
    for entry in acknowledgments.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("acknowledged_at"), str):
            raise RuntimeError(f"Invalid acknowledgment in {path}")
        for field in ["comment_urls", "commit_shas"]:
            values = entry.get(field)
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise RuntimeError(f"Invalid acknowledgment activity in {path}")
    validate_discussion_cutoffs(state.get("discussion_cutoffs", {}), path)
    return state


def validate_discussion_cutoffs(cutoffs: object, path: Path) -> None:
    if not isinstance(cutoffs, dict):
        raise RuntimeError(f"Invalid discussion cutoffs in triage state at {path}")
    for cutoff in cutoffs.values():
        try:
            if not isinstance(cutoff, str):
                raise ValueError("Cutoff must be a timestamp")
            parse_cutoff(cutoff)
        except (ValueError, argparse.ArgumentTypeError) as error:
            raise RuntimeError(f"Invalid discussion cutoff in triage state at {path}") from error


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".triage-", dir=path.parent) as directory:
        temporary_path = Path(directory) / "state.json"
        temporary_path.write_text(json.dumps(state, indent=2) + "\n")
        temporary_path.replace(path)


def acknowledgment_key(repo: str, login: str, kind: str, number: int) -> str:
    return f"{repo.casefold()}:{login.casefold()}:{kind}:{number}"


def parse_cutoff(value: str) -> datetime:
    try:
        cutoff = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use an ISO date or timestamp") from error
    return cutoff if cutoff.tzinfo else cutoff.replace(tzinfo=UTC)


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


def read_graphql(query: str, variables: dict) -> dict:
    command = ["gh", "api", "graphql", "--input", "-"]
    result = subprocess.run(  # noqa: S603 -- Fixed gh command; no shell.
        command,
        input=json.dumps({"query": query, "variables": variables}),
        check=True,
        capture_output=True,
        text=True,
    )
    response = json.loads(result.stdout)
    if response.get("errors"):
        raise RuntimeError(f"GitHub GraphQL retrieval failed: {json.dumps(response['errors'])}")
    return response["data"]


def iter_connection(query: str, variables: dict, path: list[str], cursor: str | None = None) -> Iterator[dict]:
    while True:
        connection = read_graphql(query, {**variables, "cursor": cursor})
        for field in path:
            connection = connection[field]
            if connection is None:
                raise RuntimeError(f"GitHub GraphQL returned no data for {'.'.join(path)}")
        yield from connection["nodes"]
        page_info = connection["pageInfo"]
        if not page_info["hasNextPage"]:
            return
        next_cursor = page_info["endCursor"]
        if not next_cursor or next_cursor == cursor:
            raise RuntimeError("GitHub GraphQL pagination did not advance")
        cursor = next_cursor


def collect_discussions(repo: str, label: str | None, since: datetime | None) -> list[dict]:
    owner, name = repo.split("/", maxsplit=1)
    nodes = iter_connection(DISCUSSIONS_QUERY, {"owner": owner, "name": name}, ["repository", "discussions"])
    discussions = []
    for node in nodes:
        # Newest openings come first, so no older pages or thread comments are needed.
        if since is not None and parse_time(node["createdAt"]) < since:
            break
        if node["labels"]["pageInfo"]["hasNextPage"]:
            raise RuntimeError(f"Discussion #{node['number']}: label retrieval is incomplete")
        labels = node["labels"]["nodes"]
        if label and label not in [item["name"] for item in labels]:
            continue
        author = node.get("author") or {}
        discussions.append(
            {
                "node_id": node["id"],
                "number": node["number"],
                "title": node["title"],
                "html_url": node["url"],
                "body": node["body"],
                "created_at": node["createdAt"],
                "user": {"login": author.get("login"), "type": author.get("__typename")},
                "labels": labels,
                "is_answered": node["isAnswered"],
                "category": node["category"]["name"],
            }
        )
    return discussions


def collect_discussion_comments(node_id: str) -> list[dict]:
    nodes = iter_connection(DISCUSSION_COMMENTS_QUERY, {"id": node_id}, ["node", "comments"])
    comments = []
    for node in nodes:
        replies = node["replies"]["nodes"]
        page_info = node["replies"]["pageInfo"]
        if page_info["hasNextPage"]:
            if not page_info["endCursor"]:
                raise RuntimeError("GitHub GraphQL reply pagination has no cursor")
            replies.extend(
                iter_connection(
                    DISCUSSION_REPLIES_QUERY,
                    {"id": node["id"]},
                    ["node", "replies"],
                    page_info["endCursor"],
                ),
            )
        for item in [node, *replies]:
            if not item["body"].strip():
                continue
            author = item.get("author") or {}
            login = author.get("login") or "[deleted]"
            comments.append(
                {
                    "kind": "discussion_comment" if item is node else "discussion_reply",
                    "author": login,
                    "is_bot": author.get("__typename") == "Bot" or login.endswith("[bot]"),
                    "created_at": item["createdAt"],
                    "url": item["url"],
                    "body": item["body"],
                }
            )
    comments.sort(key=lambda comment: parse_time(comment["created_at"]))
    return comments


def collect_comments(repo: str, number: int, *, is_pr: bool = True) -> list[dict]:
    sources = [
        ["discussion", f"repos/{repo}/issues/{number}/comments", "created_at"],
    ]
    if is_pr:
        sources.extend(
            [
                ["inline_review", f"repos/{repo}/pulls/{number}/comments", "created_at"],
                ["review", f"repos/{repo}/pulls/{number}/reviews", "submitted_at"],
            ],
        )
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


def collect_commits(repo: str, number: int) -> list[dict]:
    items = read_api(f"repos/{repo}/pulls/{number}/commits?per_page=100", paginate=True)
    # GitHub caps this endpoint at 250 commits, even when paginating.
    if len(items) >= 250:
        raise RuntimeError(f"PR #{number}: commit retrieval may be incomplete (GitHub's 250-commit limit)")
    commits = []
    for item in items:
        commit = item["commit"]
        author = item.get("author") or {}
        login = author.get("login") or commit["author"]["name"]
        commits.append(
            {
                "sha": item["sha"],
                "author": login,
                "is_bot": author.get("type") == "Bot" or login.endswith("[bot]"),
                "committed_at": commit["committer"]["date"],
                "url": item["html_url"],
                "message": commit["message"],
            }
        )
    commits.sort(key=lambda commit: parse_time(commit["committed_at"]))
    return commits


def find_latest_response(item: dict, comments: list[dict], login: str) -> dict | None:
    """Include an item opened by the selected user as their initial response."""
    own_comments = [comment for comment in comments if comment["author"].casefold() == login.casefold()]
    author = (item.get("user") or {}).get("login") or "[deleted]"
    if author.casefold() == login.casefold():
        own_comments.append(
            {
                "kind": "opening",
                "author": author,
                "is_bot": False,
                "created_at": item["created_at"],
                "url": item["html_url"],
                "body": item.get("body") or "",
            }
        )
    return max(own_comments, key=lambda comment: parse_time(comment["created_at"])) if own_comments else None


def determine_status(item: dict, has_response: bool, new_comments: list[dict], new_commits: list[dict]) -> str:
    labels = [label["name"] for label in item.get("labels", [])]
    if item.get("draft"):
        return "draft"
    if not has_response:
        if "waiting-for-author" in labels:
            return "no_baseline"
        if item.get("is_answered"):
            return "answered"
        return "new_incoming"
    has_human_comments = any(not comment["is_bot"] for comment in new_comments)
    has_human_commits = any(not commit["is_bot"] for commit in new_commits)
    if has_human_comments and has_human_commits:
        return "new_human_comments_and_commits"
    if has_human_comments:
        return "new_human_comments"
    if has_human_commits:
        return "new_commits"
    if new_comments or new_commits:
        return "bot_only"
    return "waiting_for_author" if "waiting-for-author" in labels else "no_new_activity"


def summarize_item(
    item: dict,
    comments: list[dict],
    commits: list[dict],
    login: str,
    kind: str = "pr",
    acknowledgment: dict | None = None,
) -> dict:
    latest_own = find_latest_response(item, comments, login)
    author = (item.get("user") or {}).get("login") or "[deleted]"
    new_comments = []
    new_commits = []
    if latest_own or acknowledgment:
        cutoff = parse_time(latest_own["created_at"]) if latest_own else datetime.min.replace(tzinfo=UTC)
        new_comments = [
            comment
            for comment in comments
            if comment["author"].casefold() != login.casefold() and parse_time(comment["created_at"]) > cutoff
        ]
        new_commits = [commit for commit in commits if parse_time(commit["committed_at"]) > cutoff]
    if acknowledgment:
        handled_urls = set(acknowledgment["comment_urls"])
        handled_shas = set(acknowledgment["commit_shas"])
        new_comments = [comment for comment in new_comments if comment["url"] not in handled_urls]
        new_commits = [commit for commit in new_commits if commit["sha"] not in handled_shas]
    status = determine_status(item, latest_own is not None or acknowledgment is not None, new_comments, new_commits)
    if acknowledgment and status not in ATTENTION_STATUSES and status != "draft":
        status = "handled"
    needs_attention = status in ATTENTION_STATUSES
    if status == "draft":
        needs_attention = (latest_own is None and acknowledgment is None) or any(
            not comment["is_bot"] for comment in new_comments
        )
    activity_times = [comment["created_at"] for comment in comments if not comment["is_bot"]]
    activity_times.extend(commit["committed_at"] for commit in commits if not commit["is_bot"])
    if item.get("created_at"):
        activity_times.append(item["created_at"])
    return {
        "kind": kind,
        "number": item["number"],
        "title": item["title"],
        "url": item["html_url"],
        "author": author,
        "author_is_bot": (item.get("user") or {}).get("type") == "Bot" or author.endswith("[bot]"),
        "created_at": item.get("created_at"),
        "latest_activity_at": max(activity_times, key=parse_time) if activity_times else None,
        "body": item.get("body") or "",
        "labels": [label["name"] for label in item.get("labels", [])],
        "category": item.get("category"),
        "is_answered": item.get("is_answered", False),
        "status": status,
        "needs_attention": needs_attention,
        "latest_user_comment": latest_own,
        "acknowledged_at": acknowledgment["acknowledged_at"] if acknowledgment else None,
        "activity_snapshot": {
            "comment_urls": [comment["url"] for comment in comments],
            "commit_shas": [commit["sha"] for commit in commits],
        },
        "context_comments": comments if latest_own is None and acknowledgment is None else [],
        "new_comments": new_comments,
        "new_commits": new_commits,
    }


def should_scan_item(item: dict, numbers: list[int] | None, before: datetime | None) -> bool:
    if numbers is not None and item["number"] not in numbers:
        return False
    return before is None or parse_time(item["created_at"]) < before


def create_item_report(repo: str, login: str, kind: str, item: dict, acknowledgments: dict[str, dict]) -> dict:
    print(f"Checking {kind} #{item['number']}: {item['title']}", file=sys.stderr)
    if kind == "discussion":
        comments = collect_discussion_comments(item["node_id"])
    else:
        comments = collect_comments(repo, item["number"], is_pr=kind == "pr")
    commits = collect_commits(repo, item["number"]) if kind == "pr" else []
    key = acknowledgment_key(repo, login, kind, item["number"])
    return summarize_item(item, comments, commits, login, kind, acknowledgments.get(key))


def collect_reports(
    args: argparse.Namespace, login: str, acknowledgments: dict[str, dict], discussions_since: datetime | None
) -> list[dict]:
    reports = []
    if "pr" in args.kind or "issue" in args.kind:
        parameters = {"state": "open"}
        if args.label:
            parameters["labels"] = args.label
        parameters["per_page"] = 100
        query = urlencode(parameters)
        for item in read_api(f"repos/{args.repo}/issues?{query}", paginate=True):
            kind = "pr" if "pull_request" in item else "issue"
            if kind in args.kind and should_scan_item(item, args.acknowledge, args.acknowledge_before):
                reports.append(create_item_report(args.repo, login, kind, item, acknowledgments))
    if "discussion" in args.kind:
        for item in collect_discussions(args.repo, args.label, discussions_since):
            if should_scan_item(item, args.acknowledge, args.acknowledge_before):
                # Keep serial API requests and progress reporting explicit.
                reports.append(create_item_report(args.repo, login, "discussion", item, acknowledgments))  # noqa: PERF401
    if args.acknowledge:
        missing = set(args.acknowledge) - {report["number"] for report in reports}
        if missing:
            raise RuntimeError(f"Requested items are not open or do not match the filters: {sorted(missing)}")
    return reports


def acknowledge_reports(reports: list[dict], repo: str, login: str, acknowledgments: dict[str, dict]) -> None:
    timestamp = datetime.now(UTC).isoformat()
    for report in reports:
        key = acknowledgment_key(repo, login, report["kind"], report["number"])
        acknowledgments[key] = {"acknowledged_at": timestamp, **report["activity_snapshot"]}
        report.update(
            status="handled",
            needs_attention=False,
            acknowledged_at=timestamp,
            new_comments=[],
            new_commits=[],
            context_comments=[],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="bramstroker/homeassistant-powercalc")
    parser.add_argument("--label", help="Restrict all selected kinds to an exact label (default: all labels)")
    parser.add_argument(
        "--kind", nargs="+", choices=["pr", "issue", "discussion"], default=["pr", "issue", "discussion"]
    )
    parser.add_argument("--login")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH, help="Local acknowledgment file")
    parser.add_argument(
        "--ignore-discussions-before",
        type=parse_cutoff,
        metavar="DATE_OR_TIMESTAMP",
        help="Save a permanent opening-date cutoff for discussions in the local state",
    )
    acknowledgment_options = parser.add_mutually_exclusive_group()
    acknowledgment_options.add_argument("--acknowledge", nargs="+", type=int, metavar="NUMBER")
    acknowledgment_options.add_argument(
        "--acknowledge-before",
        type=parse_cutoff,
        metavar="DATE_OR_TIMESTAMP",
        help="Acknowledge selected open items created strictly before this time; dates default to UTC",
    )
    args = parser.parse_args()
    is_acknowledging = args.acknowledge is not None or args.acknowledge_before is not None
    if is_acknowledging and len(set(args.kind)) != 1:
        parser.error("Acknowledgment requires exactly one --kind: pr, issue, or discussion")
    state = read_state(args.state)
    acknowledgments = state["acknowledgments"]
    login = args.login or read_api("user")["login"]
    scope = f"{args.repo.casefold()}:{login.casefold()}"
    saved_cutoff = state.get("discussion_cutoffs", {}).get(scope)
    discussions_since = args.ignore_discussions_before or (parse_cutoff(saved_cutoff) if saved_cutoff else None)
    if args.ignore_discussions_before is not None:
        state.setdefault("discussion_cutoffs", {})[scope] = discussions_since.isoformat()
    # Verify the exact label so a typo cannot silently produce an empty report.
    if args.label:
        read_api(f"repos/{args.repo}/labels/{quote(args.label, safe='')}")
    reports = collect_reports(args, login, acknowledgments, discussions_since)
    if is_acknowledging and reports:
        acknowledge_reports(reports, args.repo, login, acknowledgments)
    if (is_acknowledging and reports) or args.ignore_discussions_before is not None:
        write_state(args.state, state)
    counts = {}
    for report in reports:
        status = report["status"]
        counts[status] = counts.get(status, 0) + 1
    by_kind = {kind: [report for report in reports if report["kind"] == kind] for kind in args.kind}
    print(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "repository": args.repo,
                "label": args.label,
                "kinds": args.kind,
                "commit_time_basis": "committer_date",
                "login": login,
                "state_path": str(args.state),
                "discussions_ignored_before": discussions_since.isoformat() if discussions_since else None,
                "acknowledged_count": len(reports) if is_acknowledging else 0,
                "total_items": len(reports),
                "total_prs": len(by_kind.get("pr", [])),
                "attention_counts": {
                    kind: sum(report["needs_attention"] for report in items) for kind, items in by_kind.items()
                },
                "counts": counts,
                "pull_requests": by_kind.get("pr", []),
                "issues": by_kind.get("issue", []),
                "discussions": by_kind.get("discussion", []),
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
    except (RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
