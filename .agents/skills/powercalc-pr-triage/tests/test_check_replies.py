"""Exercise reply triage and the CLI without accessing GitHub."""

# ruff: noqa: INP001, PT009, PT027 -- Standalone unittest suite with no third-party dependencies.

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_replies.py"
REPO = "bramstroker/homeassistant-powercalc"


def create_comment(author: str, day: int, **attributes: object) -> dict:
    return {
        "body": f"Comment from {author}",
        "created_at": f"2026-10-{day:02}T12:00:00Z",
        "user": {"login": author, "type": "User"},
        "html_url": f"https://github.com/{REPO}/pull/1#comment-{author}-{day}",
        **attributes,
    }


def create_commit(login: str, day: int, **attributes: object) -> dict:
    return {
        "sha": f"{day:040x}",
        "author": {"login": login, "type": "User"},
        "html_url": f"https://github.com/{REPO}/commit/{day:040x}",
        "commit": {
            "author": {"name": login, "date": "2026-09-01T12:00:00Z"},
            "committer": {"date": f"2026-10-{day:02}T12:00:00Z"},
            "message": "Apply review suggestions\n\nUpdate the profile metadata.",
        },
        **attributes,
    }


def create_connection(nodes: list[dict], next_cursor: str | None = None) -> dict:
    return {"nodes": nodes, "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor}}


def create_discussion(number: int, **attributes: object) -> dict:
    return {
        "id": f"d{number}",
        "number": number,
        "title": f"Discussion {number}",
        "url": f"https://github.com/{REPO}/discussions/{number}",
        "body": "Help with my device",
        "createdAt": "2026-10-01T12:00:00Z",
        "author": {"login": "contributor", "__typename": "User"},
        "labels": create_connection([]),
        "category": {"name": "Q&A"},
        "isAnswered": False,
        **attributes,
    }


def create_discussion_comment(login: str, day: int, **attributes: object) -> dict:
    return {
        "id": f"c{day}",
        "body": f"Comment from {login}",
        "createdAt": f"2026-10-{day:02}T12:00:00Z",
        "url": f"https://github.com/{REPO}/discussions/9#discussioncomment-{day}",
        "author": {"login": login, "__typename": "User"},
        "replies": create_connection([]),
        **attributes,
    }


class CheckRepliesTest(unittest.TestCase):
    def run_cli(
        self,
        responses: dict,
        arguments: list[str] | None = None,
        expected_error: str | None = None,
        state_path: Path | None = None,
        expected_exit_code: int = 1,
    ) -> dict:
        stdout = StringIO()
        stderr = StringIO()

        def run_gh(command: list[str], **options: object) -> subprocess.CompletedProcess:
            if command == ["gh", "api", "graphql", "--input", "-"]:
                payload = json.loads(options.pop("input"))
                query = payload["query"]
                variables = payload["variables"]
                if "discussions(first:" in query:
                    operation = "discussions"
                    self.assertEqual(variables["owner"], "bramstroker")
                    self.assertEqual(variables["name"], "homeassistant-powercalc")
                    self.assertIn("states: [OPEN]", query)
                    self.assertIn("field: CREATED_AT, direction: DESC", query)
                elif "... on DiscussionComment" in query:
                    operation = "replies"
                else:
                    operation = "comments"
                response = responses[(operation, variables.get("id"), variables["cursor"])]
                self.assertEqual(options, {"check": True, "capture_output": True, "text": True})
                if isinstance(response, Exception):
                    raise response
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(response), stderr="")
            endpoint = command[4]
            response = responses[endpoint]
            if isinstance(response, Exception):
                raise response
            self.assertEqual(command[:4], ["gh", "api", "--method", "GET"])
            self.assertEqual(options, {"check": True, "capture_output": True, "text": True})
            if isinstance(response, list):
                self.assertEqual(command[5:], ["--paginate", "--slurp"])
            else:
                self.assertEqual(command[5:], [])
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(response), stderr="")

        with (
            TemporaryDirectory() as directory,
            patch.object(
                sys,
                "argv",
                [
                    str(SCRIPT),
                    *(arguments if arguments is not None else ["--kind", "pr", "--label", "waiting-for-author"]),
                    "--state",
                    str(state_path or Path(directory) / "state.json"),
                ],
            ),
            patch("subprocess.run", side_effect=run_gh),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as result,
        ):
            runpy.run_path(str(SCRIPT), run_name="__main__")
        if expected_error:
            self.assertEqual(result.exception.code, expected_exit_code)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(expected_error, stderr.getvalue())
            return {}
        self.assertEqual(result.exception.code, 0)
        return json.loads(stdout.getvalue())

    def test_paginated_scan_includes_all_comment_sources_and_statuses(self) -> None:
        prs = [
            {
                "number": number,
                "title": f"Profile {number}",
                "html_url": f"https://github.com/{REPO}/pull/{number}",
                "pull_request": {},
                "user": {"login": "contributor"},
                "labels": [{"name": "waiting-for-author"}],
            }
            for number in range(1, 9)
        ]
        responses = {
            "user": {"login": "BRAMSTROKER"},
            f"repos/{REPO}/labels/waiting-for-author": {},
            f"repos/{REPO}/issues?state=open&labels=waiting-for-author&per_page=100": [
                [*prs[:2], {"number": 99, "title": "An issue"}],
                prs[2:],
            ],
        }
        for pr in prs:
            number = pr["number"]
            responses[f"repos/{REPO}/issues/{number}/comments?per_page=100"] = [
                [create_comment("bramstroker", 1)],
            ]
            responses[f"repos/{REPO}/pulls/{number}/comments?per_page=100"] = [[]]
            responses[f"repos/{REPO}/pulls/{number}/reviews?per_page=100"] = [[]]
            responses[f"repos/{REPO}/pulls/{number}/commits?per_page=100"] = [[create_commit("contributor", 1)]]

        # A reply on another comment page and a later inline reply both count.
        responses[f"repos/{REPO}/issues/1/comments?per_page=100"].append([create_comment("contributor", 2)])
        responses[f"repos/{REPO}/pulls/1/comments?per_page=100"] = [[create_comment("contributor", 3)]]
        # Bot type and bot-login suffix are both recognized.
        responses[f"repos/{REPO}/issues/2/comments?per_page=100"].append(
            [
                create_comment("automation", 2, user={"login": "automation", "type": "Bot"}),
                create_comment("ci[bot]", 3),
            ],
        )
        # An equal-time reply is not strictly after the cutoff.
        responses[f"repos/{REPO}/issues/3/comments?per_page=100"].append([create_comment("contributor", 1)])
        # No comment by the selected user means there is no comparison baseline.
        responses[f"repos/{REPO}/issues/4/comments?per_page=100"] = [[create_comment("contributor", 2)]]
        responses[f"repos/{REPO}/pulls/4/commits?per_page=100"] = [[create_commit("contributor", 4)]]
        # Review summaries can advance the cutoff; blank/pending reviews cannot.
        responses[f"repos/{REPO}/issues/5/comments?per_page=100"].append([create_comment("contributor", 2)])
        responses[f"repos/{REPO}/pulls/5/reviews?per_page=100"] = [
            [
                create_comment("bramstroker", 3, submitted_at="2026-10-03T12:00:00Z"),
                create_comment("bramstroker", 4, body=" ", submitted_at="2026-10-04T12:00:00Z"),
                create_comment("bramstroker", 5, submitted_at=None),
                create_comment("contributor", 4, submitted_at="2026-10-04T12:00:00Z"),
                create_comment("removed", 5, user=None, submitted_at="2026-10-05T12:00:00Z"),
            ],
        ]
        # Commits use committer dates, including old-authored/rebased commits.
        # All pages are included and sorted, and equal-time commits are excluded.
        responses[f"repos/{REPO}/pulls/6/commits?per_page=100"] = [
            [create_commit("contributor", 3), create_commit("contributor", 1)],
            [create_commit("Unknown contributor", 2, author=None)],
        ]
        responses[f"repos/{REPO}/issues/7/comments?per_page=100"].append([create_comment("contributor", 2)])
        responses[f"repos/{REPO}/pulls/7/commits?per_page=100"] = [[create_commit("contributor", 2)]]
        responses[f"repos/{REPO}/pulls/8/commits?per_page=100"] = [
            [
                create_commit("automation", 2, author={"login": "automation", "type": "Bot"}),
                create_commit("ci[bot]", 3),
            ],
        ]

        report = self.run_cli(responses)
        self.assertEqual(report["total_prs"], 8)
        self.assertEqual(report["login"], "BRAMSTROKER")
        self.assertEqual(report["repository"], REPO)
        self.assertEqual(report["label"], "waiting-for-author")
        self.assertEqual(report["commit_time_basis"], "committer_date")
        self.assertEqual(
            report["counts"],
            {
                "new_human_comments": 2,
                "bot_only": 2,
                "waiting_for_author": 1,
                "no_baseline": 1,
                "new_commits": 1,
                "new_human_comments_and_commits": 1,
            },
        )
        first, bot_only, same_time, no_baseline, reviews, commits, combined, bot_commits = report["pull_requests"]
        self.assertEqual([comment["kind"] for comment in first["new_comments"]], ["discussion", "inline_review"])
        self.assertEqual([comment["author"] for comment in bot_only["new_comments"]], ["automation", "ci[bot]"])
        self.assertEqual(same_time["new_comments"], [])
        self.assertEqual(same_time["new_commits"], [])
        self.assertIsNone(no_baseline["latest_user_comment"])
        self.assertEqual(no_baseline["new_comments"], [])
        self.assertEqual(no_baseline["new_commits"], [])
        self.assertEqual(no_baseline["context_comments"][0]["author"], "contributor")
        self.assertEqual(no_baseline["latest_activity_at"], "2026-10-04T12:00:00Z")
        self.assertEqual(reviews["latest_user_comment"]["created_at"], "2026-10-03T12:00:00Z")
        self.assertEqual([comment["author"] for comment in reviews["new_comments"]], ["contributor", "[deleted]"])
        self.assertEqual(reviews["new_comments"][0]["body"], "Comment from contributor")
        self.assertIn("#comment-contributor-4", reviews["new_comments"][0]["url"])
        self.assertEqual(
            [commit["author"] for commit in commits["new_commits"]], ["Unknown contributor", "contributor"]
        )
        self.assertEqual(commits["new_comments"], [])
        self.assertEqual(commits["new_commits"][0]["sha"], f"{2:040x}")
        self.assertEqual(commits["new_commits"][0]["url"], f"https://github.com/{REPO}/commit/{2:040x}")
        self.assertEqual(commits["new_commits"][0]["committed_at"], "2026-10-02T12:00:00Z")
        self.assertIn("Update the profile metadata.", commits["new_commits"][0]["message"])
        self.assertEqual(len(combined["new_comments"]), 1)
        self.assertEqual(len(combined["new_commits"]), 1)
        self.assertTrue(all(commit["is_bot"] for commit in bot_commits["new_commits"]))

    def test_overrides_and_empty_repository(self) -> None:
        report = self.run_cli(
            {
                "repos/example/repo/labels/needs%20reply": {},
                "repos/example/repo/issues?state=open&labels=needs+reply&per_page=100": [[]],
            },
            ["--repo", "example/repo", "--label", "needs reply", "--login", "someone", "--kind", "pr"],
        )
        self.assertEqual(report["total_prs"], 0)
        self.assertEqual(report["pull_requests"], [])
        self.assertEqual(report["counts"], {})
        self.assertEqual(report["login"], "someone")

    def test_api_failure_does_not_emit_a_partial_report(self) -> None:
        for error_text in ["GitHub rate limit exceeded", None]:
            with self.subTest(stderr=error_text):
                stdout = StringIO()
                stderr = StringIO()
                error = subprocess.CalledProcessError(1, ["gh", "api"], stderr=error_text)
                with (
                    patch.object(sys, "argv", [str(SCRIPT), "--login", "someone"]),
                    patch("subprocess.run", side_effect=error),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                    self.assertRaises(SystemExit) as result,
                ):
                    runpy.run_path(str(SCRIPT), run_name="__main__")
                self.assertEqual(result.exception.code, 1)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn(error_text or str(error), stderr.getvalue())

    def test_review_summary_can_be_the_latest_user_comment(self) -> None:
        namespace = runpy.run_path(str(SCRIPT))
        responses = [
            [create_comment("bramstroker", 1)],
            [create_comment("contributor", 2)],
            [create_comment("bramstroker", 3, submitted_at="2026-10-03T14:00:00+02:00")],
        ]
        with patch.dict(namespace["collect_comments"].__globals__, read_api=lambda *args, **kwargs: responses.pop(0)):
            comments = namespace["collect_comments"](REPO, 1)
        commits = [{"sha": "same-time", "committed_at": "2026-10-03T14:00:00+02:00", "is_bot": False}]
        report = namespace["summarize_item"](
            {"number": 1, "title": "Profile", "html_url": "pr"}, comments, commits, "bramstroker"
        )
        self.assertEqual(report["status"], "no_new_activity")
        self.assertEqual(report["latest_user_comment"]["kind"], "review")
        self.assertEqual(report["new_comments"], [])
        self.assertEqual(report["new_commits"], [])

    def test_commit_api_failure_does_not_emit_a_partial_report(self) -> None:
        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="Commit retrieval failed")
        self.assert_cli_failure_on_commits(error, "Commit retrieval failed")

    def test_commit_limit_does_not_emit_a_partial_report(self) -> None:
        self.assert_cli_failure_on_commits([create_commit("contributor", 1)] * 250, "250-commit limit")

    def assert_cli_failure_on_commits(self, commits_response: object, expected_error: str) -> None:
        self.run_cli(
            {
                "user": {"login": "bramstroker"},
                f"repos/{REPO}/labels/waiting-for-author": {},
                f"repos/{REPO}/issues?state=open&labels=waiting-for-author&per_page=100": [
                    [{"number": 1, "title": "Profile", "pull_request": {}}],
                ],
                f"repos/{REPO}/issues/1/comments?per_page=100": [[]],
                f"repos/{REPO}/pulls/1/comments?per_page=100": [[]],
                f"repos/{REPO}/pulls/1/reviews?per_page=100": [[]],
                f"repos/{REPO}/pulls/1/commits?per_page=100": (
                    commits_response if isinstance(commits_response, Exception) else [commits_response]
                ),
            },
            expected_error=expected_error,
        )

    def test_default_scan_includes_incoming_prs_issues_and_nested_discussion_replies(self) -> None:
        items = [
            {
                "number": number,
                "title": f"Item {number}",
                "html_url": f"https://github.com/{REPO}/issues/{number}",
                "created_at": "2026-10-01T12:00:00Z",
                "body": "Please help with this device",
                "user": {"login": "contributor"},
            }
            for number in range(1, 8)
        ]
        for index in [0, 1, 2, 6]:
            items[index]["pull_request"] = {}
        items[1]["labels"] = [{"name": "waiting-for-author"}]
        items[2]["user"] = {"login": "release[bot]", "type": "Bot"}
        items[3]["user"] = {"login": "BRAMSTROKER"}
        items[5]["labels"] = [{"name": "waiting-for-author"}]
        items[6]["draft"] = True
        responses = {
            "user": {"login": "bramstroker"},
            f"repos/{REPO}/issues?state=open&per_page=100": [items[:3], items[3:]],
        }
        for item in items:
            number = item["number"]
            responses[f"repos/{REPO}/issues/{number}/comments?per_page=100"] = [[]]
            if "pull_request" in item:
                responses[f"repos/{REPO}/pulls/{number}/comments?per_page=100"] = [[]]
                responses[f"repos/{REPO}/pulls/{number}/reviews?per_page=100"] = [[]]
                responses[f"repos/{REPO}/pulls/{number}/commits?per_page=100"] = [[]]
        responses[f"repos/{REPO}/issues/2/comments?per_page=100"] = [
            [create_comment("bramstroker", 1), create_comment("contributor", 2)],
        ]
        responses[f"repos/{REPO}/issues/4/comments?per_page=100"] = [[create_comment("contributor", 2)]]

        discussions = [create_discussion(number) for number in range(8, 13)]
        discussions[2]["isAnswered"] = True
        discussions[3]["labels"] = create_connection([{"name": "waiting-for-author"}])
        discussions[4]["author"] = {"login": "bramstroker", "__typename": "User"}
        responses[("discussions", None, None)] = {
            "data": {"repository": {"discussions": create_connection(discussions[:2], "d-next")}},
        }
        responses[("discussions", None, "d-next")] = {
            "data": {"repository": {"discussions": create_connection(discussions[2:])}},
        }
        for discussion in discussions:
            responses[("comments", discussion["id"], None)] = {
                "data": {"node": {"comments": create_connection([])}},
            }
        responses[("comments", "d11", None)] = {
            "data": {"node": {"comments": create_connection([create_discussion_comment("bramstroker", 1)])}},
        }
        responses[("comments", "d9", None)] = {
            "data": {
                "node": {
                    "comments": create_connection(
                        [
                            create_discussion_comment(
                                "bramstroker",
                                1,
                                replies=create_connection([create_discussion_comment("bramstroker", 2)], "r-next"),
                            ),
                        ],
                        "c-next",
                    ),
                },
            },
        }
        responses[("comments", "d9", "c-next")] = {
            "data": {"node": {"comments": create_connection([create_discussion_comment("contributor", 1)])}},
        }
        responses[("replies", "c1", "r-next")] = {
            "data": {"node": {"replies": create_connection([create_discussion_comment("contributor", 3)])}},
        }

        report = self.run_cli(responses, [])
        self.assertIsNone(report["label"])
        self.assertEqual(report["kinds"], ["pr", "issue", "discussion"])
        self.assertEqual(report["total_items"], 12)
        self.assertEqual(report["total_prs"], 4)
        self.assertEqual(report["attention_counts"], {"pr": 4, "issue": 3, "discussion": 2})
        incoming_pr, follow_up, bot_pr, draft = report["pull_requests"]
        self.assertEqual(incoming_pr["status"], "new_incoming")
        self.assertEqual(incoming_pr["body"], "Please help with this device")
        self.assertEqual(follow_up["status"], "new_human_comments")
        self.assertTrue(bot_pr["author_is_bot"])
        self.assertTrue(bot_pr["needs_attention"])
        self.assertEqual(draft["status"], "draft")
        self.assertTrue(draft["needs_attention"])
        own_issue, incoming_issue, no_baseline = report["issues"]
        self.assertEqual(own_issue["latest_user_comment"]["kind"], "opening")
        self.assertEqual(own_issue["status"], "new_human_comments")
        self.assertEqual(incoming_issue["status"], "new_incoming")
        self.assertEqual(no_baseline["status"], "no_baseline")
        incoming_discussion, replies, answered, waiting, own_discussion = report["discussions"]
        self.assertEqual(incoming_discussion["status"], "new_incoming")
        self.assertEqual(incoming_discussion["category"], "Q&A")
        self.assertEqual(replies["latest_user_comment"]["created_at"], "2026-10-02T12:00:00Z")
        self.assertEqual(replies["latest_user_comment"]["kind"], "discussion_reply")
        self.assertEqual([comment["kind"] for comment in replies["new_comments"]], ["discussion_reply"])
        self.assertEqual(replies["status"], "new_human_comments")
        self.assertEqual(replies["latest_activity_at"], "2026-10-03T12:00:00Z")
        self.assertEqual(replies["context_comments"], [])
        self.assertEqual(answered["status"], "answered")
        self.assertFalse(answered["needs_attention"])
        self.assertEqual(waiting["status"], "waiting_for_author")
        self.assertFalse(waiting["needs_attention"])
        self.assertEqual(own_discussion["status"], "no_new_activity")

    def test_drafts_need_first_responses_and_human_follow_ups(self) -> None:
        items = [
            {
                "number": number,
                "title": f"Draft {number}",
                "html_url": f"https://github.com/{REPO}/pull/{number}",
                "created_at": "2026-10-01T12:00:00Z",
                "body": "Could you advise on the measurement setup?",
                "user": {"login": "contributor"},
                "pull_request": {},
                "draft": True,
            }
            for number in range(1, 6)
        ]
        items[4]["user"] = {"login": "bramstroker"}
        responses = {
            "user": {"login": "bramstroker"},
            f"repos/{REPO}/issues?state=open&per_page=100": [items],
        }
        for item in items:
            number = item["number"]
            responses[f"repos/{REPO}/issues/{number}/comments?per_page=100"] = [[]]
            responses[f"repos/{REPO}/pulls/{number}/comments?per_page=100"] = [[]]
            responses[f"repos/{REPO}/pulls/{number}/reviews?per_page=100"] = [[]]
            responses[f"repos/{REPO}/pulls/{number}/commits?per_page=100"] = [[]]
        for number in [2, 3, 4]:
            responses[f"repos/{REPO}/issues/{number}/comments?per_page=100"] = [
                [create_comment("bramstroker", 2)],
            ]
        responses[f"repos/{REPO}/pulls/3/comments?per_page=100"] = [[create_comment("contributor", 3)]]
        responses[f"repos/{REPO}/issues/4/comments?per_page=100"][0].append(create_comment("ci[bot]", 3))
        responses[f"repos/{REPO}/pulls/4/commits?per_page=100"] = [[create_commit("contributor", 4)]]

        report = self.run_cli(responses, ["--kind", "pr"])

        self.assertEqual(report["counts"], {"draft": 5})
        self.assertEqual(report["attention_counts"], {"pr": 2})
        self.assertEqual(
            [item["needs_attention"] for item in report["pull_requests"]],
            [True, False, True, False, False],
        )
        self.assertEqual(report["pull_requests"][2]["new_comments"][0]["author"], "contributor")

    def test_acknowledged_draft_returns_when_a_new_human_comment_arrives(self) -> None:
        summarize = runpy.run_path(str(SCRIPT))["summarize_item"]
        item = {
            "number": 1,
            "title": "Draft profile",
            "html_url": f"https://github.com/{REPO}/pull/1",
            "created_at": "2026-10-01T12:00:00Z",
            "user": {"login": "contributor"},
            "draft": True,
        }
        acknowledgment = {"acknowledged_at": "2026-10-02T12:00:00Z", "comment_urls": [], "commit_shas": []}
        report = summarize(item, [], [], "bramstroker", acknowledgment=acknowledgment)
        self.assertFalse(report["needs_attention"])

        comment = {
            "author": "contributor",
            "is_bot": False,
            "created_at": "2026-10-03T12:00:00Z",
            "url": f"https://github.com/{REPO}/pull/1#new-question",
            "body": "Can you advise on the voltage metadata?",
        }
        report = summarize(item, [comment], [], "bramstroker", acknowledgment=acknowledgment)
        self.assertEqual(report["status"], "draft")
        self.assertTrue(report["needs_attention"])
        self.assertEqual(report["new_comments"], [comment])

        acknowledgment["comment_urls"] = [comment["url"]]
        report = summarize(item, [comment], [], "bramstroker", acknowledgment=acknowledgment)
        self.assertFalse(report["needs_attention"])

    def test_discussion_label_filter_and_bot_replies(self) -> None:
        discussion = create_discussion(1, labels=create_connection([{"name": "question"}]))
        responses = {
            "user": {"login": "bramstroker"},
            f"repos/{REPO}/labels/question": {},
            ("discussions", None, None): {
                "data": {"repository": {"discussions": create_connection([discussion, create_discussion(2)])}},
            },
            ("comments", "d1", None): {
                "data": {
                    "node": {
                        "comments": create_connection(
                            [
                                create_discussion_comment("bramstroker", 1),
                                create_discussion_comment("ignored", 2, body=" "),
                                create_discussion_comment("removed", 1, author=None),
                                create_discussion_comment("ci[bot]", 2),
                                create_discussion_comment(
                                    "automation", 3, author={"login": "automation", "__typename": "Bot"}
                                ),
                            ],
                        ),
                    },
                },
            },
        }
        report = self.run_cli(responses, ["--kind", "discussion", "--label", "question"])
        self.assertEqual(report["total_items"], 1)
        self.assertEqual(report["attention_counts"], {"discussion": 0})
        self.assertEqual(report["discussions"][0]["status"], "bot_only")
        self.assertEqual(
            [comment["author"] for comment in report["discussions"][0]["new_comments"]], ["ci[bot]", "automation"]
        )

    def test_graphql_failures_do_not_emit_partial_reports(self) -> None:
        cases = [
            ({"data": {"repository": None}}, "returned no data"),
            ({"data": {}, "errors": [{"message": "Permission denied"}]}, "Permission denied"),
            (
                {
                    "data": {
                        "repository": {
                            "discussions": {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": None}}
                        }
                    }
                },
                "pagination did not advance",
            ),
            ({"data": {"repository": {"discussions": create_connection([], "same")}}}, "pagination did not advance"),
            (subprocess.CalledProcessError(1, ["gh", "api"], stderr="GraphQL failed"), "GraphQL failed"),
        ]
        for response, expected_error in cases:
            with self.subTest(error=expected_error):
                responses = {
                    ("discussions", None, None): response,
                    ("discussions", None, "same"): response,
                }
                self.run_cli(
                    responses, ["--kind", "discussion", "--login", "bramstroker"], expected_error=expected_error
                )

    def test_incomplete_discussion_labels_and_replies_fail_explicitly(self) -> None:
        for fail_labels in [True, False]:
            with self.subTest(labels=fail_labels):
                discussion = create_discussion(1)
                comment = create_discussion_comment("contributor", 1)
                if fail_labels:
                    discussion["labels"]["pageInfo"]["hasNextPage"] = True
                else:
                    comment["replies"]["pageInfo"]["hasNextPage"] = True
                self.run_cli(
                    {
                        ("discussions", None, None): {
                            "data": {"repository": {"discussions": create_connection([discussion])}}
                        },
                        ("comments", "d1", None): {"data": {"node": {"comments": create_connection([comment])}}},
                    },
                    ["--kind", "discussion", "--login", "bramstroker"],
                    expected_error="label retrieval is incomplete" if fail_labels else "reply pagination has no cursor",
                )

    def test_acknowledge_discussion_backlog_and_resurface_new_replies(self) -> None:
        discussions = [
            create_discussion(1, createdAt="2026-08-31T21:59:59Z"),
            create_discussion(2, createdAt="2026-08-31T22:00:00Z"),
            create_discussion(3, createdAt="2026-09-01T00:00:01Z"),
        ]
        comments = create_connection(
            [
                create_discussion_comment(
                    "bramstroker",
                    1,
                    replies=create_connection([create_discussion_comment("contributor", 2)]),
                ),
            ],
        )
        responses = {
            ("discussions", None, None): {"data": {"repository": {"discussions": create_connection(discussions)}}},
            ("comments", "d1", None): {"data": {"node": {"comments": comments}}},
            ("comments", "d2", None): {"data": {"node": {"comments": create_connection([])}}},
            ("comments", "d3", None): {"data": {"node": {"comments": create_connection([])}}},
        }
        arguments = ["--kind", "discussion", "--login", "bramstroker"]
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "private" / "state.json"
            acknowledgment = self.run_cli(
                responses,
                [*arguments, "--acknowledge-before", "2026-09-01T00:00:00+02:00"],
                state_path=state_path,
            )
            self.assertEqual(acknowledgment["acknowledged_count"], 1)
            self.assertEqual([item["number"] for item in acknowledgment["discussions"]], [1])
            self.assertEqual(acknowledgment["discussions"][0]["status"], "handled")
            self.assertEqual(acknowledgment["attention_counts"], {"discussion": 0})
            state = json.loads(state_path.read_text())
            key = f"{REPO}:bramstroker:discussion:1"
            self.assertEqual(len(state["acknowledgments"][key]["comment_urls"]), 2)
            self.assertEqual(state["acknowledgments"][key]["commit_shas"], [])
            saved_state = state_path.read_bytes()

            unchanged = self.run_cli(responses, arguments, state_path=state_path)
            self.assertEqual(unchanged["discussions"][0]["status"], "handled")
            self.assertEqual(unchanged["attention_counts"], {"discussion": 2})
            self.assertEqual(unchanged["acknowledged_count"], 0)
            self.assertEqual(state_path.read_bytes(), saved_state)

            comments["nodes"][0]["replies"]["nodes"].append(create_discussion_comment("ci[bot]", 5))
            bot_only = self.run_cli(responses, arguments, state_path=state_path)
            self.assertEqual(bot_only["discussions"][0]["status"], "handled")
            self.assertEqual(bot_only["attention_counts"], {"discussion": 2})

            # New identity, even with the same timestamp as a previously handled reply.
            comments["nodes"][0]["replies"]["nodes"].append(
                create_discussion_comment("contributor", 3, createdAt="2026-10-02T12:00:00Z"),
            )
            changed = self.run_cli(responses, arguments, state_path=state_path)
            discussion = changed["discussions"][0]
            self.assertEqual(discussion["status"], "new_human_comments")
            human_replies = [comment for comment in discussion["new_comments"] if not comment["is_bot"]]
            self.assertEqual(len(human_replies), 1)
            self.assertIn("discussioncomment-3", human_replies[0]["url"])
            self.assertEqual(changed["attention_counts"], {"discussion": 3})
            self.assertEqual(state_path.read_bytes(), saved_state)

    def test_permanent_discussion_cutoff_skips_old_threads_and_pages(self) -> None:
        cutoff = "2026-09-01T00:00:00+02:00"
        discussions = [
            create_discussion(3, createdAt="2026-09-01T00:00:01Z"),
            create_discussion(2, createdAt="2026-08-31T22:00:00Z"),
            create_discussion(1, createdAt="2026-08-31T21:59:59Z"),
        ]
        responses = {
            ("discussions", None, None): {
                "data": {"repository": {"discussions": create_connection(discussions[:1], "page2")}}
            },
            ("discussions", None, "page2"): {
                "data": {"repository": {"discussions": create_connection(discussions[1:], "old-page")}}
            },
            ("comments", "d2", None): {"data": {"node": {"comments": create_connection([])}}},
            ("comments", "d3", None): {"data": {"node": {"comments": create_connection([])}}},
        }
        arguments = ["--kind", "discussion", "--login", "bramstroker"]
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            initial_state = {"version": 1, "acknowledgments": {}}
            state_path.write_text(json.dumps(initial_state))
            report = self.run_cli(responses, [*arguments, "--ignore-discussions-before", cutoff], state_path=state_path)
            self.assertEqual([item["number"] for item in report["discussions"]], [3, 2])
            self.assertEqual(report["discussions_ignored_before"], cutoff)
            self.assertEqual(report["acknowledged_count"], 0)
            saved_state = state_path.read_bytes()
            self.assertEqual(json.loads(saved_state)["discussion_cutoffs"], {f"{REPO}:bramstroker": cutoff})

            # A newly posted reply on the old thread must never trigger a comments request.
            responses[("comments", "d1", None)] = subprocess.CalledProcessError(
                1, ["gh", "api"], stderr="Old thread must not be scanned"
            )
            repeated = self.run_cli(responses, arguments, state_path=state_path)
            self.assertEqual(repeated["attention_counts"], {"discussion": 2})
            self.assertEqual(state_path.read_bytes(), saved_state)

            # Acknowledging current work preserves the permanent cutoff.
            self.run_cli(responses, [*arguments, "--acknowledge", "2"], state_path=state_path)
            self.assertEqual(json.loads(state_path.read_text())["discussion_cutoffs"], {f"{REPO}:bramstroker": cutoff})

            # Cutoffs belong to a repository and login, rather than all scans sharing the file.
            responses[("discussions", None, "page2")]["data"]["repository"]["discussions"] = create_connection(
                discussions[1:]
            )
            responses[("comments", "d1", None)] = {"data": {"node": {"comments": create_connection([])}}}
            other = self.run_cli(responses, ["--kind", "discussion", "--login", "someone"], state_path=state_path)
            self.assertEqual(other["total_items"], 3)
            self.assertIsNone(other["discussions_ignored_before"])

    def test_cutoff_does_not_exclude_old_prs_or_issues(self) -> None:
        items = [
            {
                "number": number,
                "title": "Old but still open",
                "html_url": f"https://github.com/{REPO}/issues/{number}",
                "user": {"login": "contributor"},
                "created_at": "2026-08-01T12:00:00Z",
            }
            for number in [1, 2]
        ]
        items[0]["pull_request"] = {}
        responses = {
            f"repos/{REPO}/issues?state=open&per_page=100": [items],
            f"repos/{REPO}/issues/1/comments?per_page=100": [[]],
            f"repos/{REPO}/issues/2/comments?per_page=100": [[]],
            f"repos/{REPO}/pulls/1/comments?per_page=100": [[]],
            f"repos/{REPO}/pulls/1/reviews?per_page=100": [[]],
            f"repos/{REPO}/pulls/1/commits?per_page=100": [[]],
            ("discussions", None, None): {
                "data": {
                    "repository": {
                        "discussions": create_connection([create_discussion(3, createdAt="2026-08-01T12:00:00Z")])
                    }
                }
            },
        }
        report = self.run_cli(responses, ["--login", "bramstroker", "--ignore-discussions-before", "2026-09-01"])
        self.assertEqual(report["total_items"], 2)
        self.assertEqual(report["attention_counts"], {"pr": 1, "issue": 1, "discussion": 0})

    def test_failed_scan_does_not_save_permanent_cutoff(self) -> None:
        responses = {
            ("discussions", None, None): subprocess.CalledProcessError(1, ["gh", "api"], stderr="Retrieval failed"),
        }
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            original = '{"version": 1, "acknowledgments": {}}\n'
            state_path.write_text(original)
            self.run_cli(
                responses,
                ["--kind", "discussion", "--login", "bramstroker", "--ignore-discussions-before", "2026-09-01"],
                state_path=state_path,
                expected_error="Retrieval failed",
            )
            self.assertEqual(state_path.read_text(), original)

    def test_invalid_saved_cutoffs_fail_without_resetting_state(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            for cutoffs in [[], {"scope": 123}, {"scope": "not-a-date"}]:
                with self.subTest(cutoffs=cutoffs):
                    original = json.dumps({"version": 1, "acknowledgments": {}, "discussion_cutoffs": cutoffs})
                    state_path.write_text(original)
                    self.run_cli({}, ["--login", "bramstroker"], state_path=state_path, expected_error="triage state")
                    self.assertEqual(state_path.read_text(), original)

    def test_acknowledge_pr_and_resurface_new_commit_without_any_response(self) -> None:
        item = {
            "number": 1,
            "title": "New profile",
            "html_url": "https://github.com/example/repo/pull/1",
            "created_at": "2026-10-01T12:00:00Z",
            "user": {"login": "contributor"},
            "pull_request": {},
        }
        commits = [create_commit("contributor", 2)]
        responses = {
            f"repos/{REPO}/issues?state=open&per_page=100": [[item]],
            f"repos/{REPO}/issues/1/comments?per_page=100": [[]],
            f"repos/{REPO}/pulls/1/comments?per_page=100": [[]],
            f"repos/{REPO}/pulls/1/reviews?per_page=100": [[]],
            f"repos/{REPO}/pulls/1/commits?per_page=100": [commits],
        }
        arguments = ["--kind", "pr", "--login", "BRAMSTROKER"]
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            existing = {
                "version": 1,
                "acknowledgments": {
                    "example/other:bramstroker:pr:1": {"acknowledged_at": "old", "comment_urls": [], "commit_shas": []}
                },
            }
            state_path.write_text(json.dumps(existing))
            report = self.run_cli(responses, [*arguments, "--acknowledge", "1"], state_path=state_path)
            self.assertEqual(report["acknowledged_count"], 1)
            self.assertEqual(len(json.loads(state_path.read_text())["acknowledgments"]), 2)
            self.assertEqual(
                self.run_cli(responses, arguments, state_path=state_path)["pull_requests"][0]["status"],
                "handled",
            )
            commits.append(create_commit("contributor", 3))
            changed = self.run_cli(responses, arguments, state_path=state_path)["pull_requests"][0]
            self.assertEqual(changed["status"], "new_commits")
            self.assertEqual([commit["sha"] for commit in changed["new_commits"]], [f"{3:040x}"])

            other_user = self.run_cli(responses, ["--kind", "pr", "--login", "someone"], state_path=state_path)
            self.assertEqual(other_user["pull_requests"][0]["status"], "new_incoming")
            del item["pull_request"]
            other_kind = self.run_cli(responses, ["--kind", "issue", "--login", "bramstroker"], state_path=state_path)
            self.assertEqual(other_kind["issues"][0]["status"], "new_incoming")

    def test_failed_bulk_acknowledgment_preserves_state(self) -> None:
        discussions = [create_discussion(1), create_discussion(2)]
        responses = {
            ("discussions", None, None): {"data": {"repository": {"discussions": create_connection(discussions)}}},
            ("comments", "d1", None): {"data": {"node": {"comments": create_connection([])}}},
            ("comments", "d2", None): subprocess.CalledProcessError(1, ["gh", "api"], stderr="Reply retrieval failed"),
        }
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            original = '{"version": 1, "acknowledgments": {}}\n'
            state_path.write_text(original)
            self.run_cli(
                responses,
                ["--kind", "discussion", "--login", "bramstroker", "--acknowledge-before", "2026-11-01"],
                expected_error="Reply retrieval failed",
                state_path=state_path,
            )
            self.assertEqual(state_path.read_text(), original)

    def test_no_matching_items_does_not_create_state(self) -> None:
        responses = {
            ("discussions", None, None): {
                "data": {"repository": {"discussions": create_connection([create_discussion(1)])}}
            },
        }
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            report = self.run_cli(
                responses,
                ["--kind", "discussion", "--login", "bramstroker", "--acknowledge-before", "2026-09-01"],
                state_path=state_path,
            )
            self.assertEqual(report["acknowledged_count"], 0)
            self.assertFalse(state_path.exists())
            self.run_cli(
                responses,
                ["--kind", "discussion", "--login", "bramstroker", "--acknowledge", "2"],
                state_path=state_path,
                expected_error="Requested items are not open",
            )
            self.assertFalse(state_path.exists())

    def test_invalid_acknowledgment_arguments(self) -> None:
        cases = [
            (["--acknowledge", "1"], "requires exactly one --kind"),
            (["--kind", "discussion", "--acknowledge-before", "bad-date"], "Use an ISO date"),
            (["--kind", "discussion", "--acknowledge-before", "2026-09-01", "--acknowledge", "1"], "not allowed"),
        ]
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                self.run_cli({}, arguments, expected_error=message, expected_exit_code=2)

    def test_invalid_state_fails_without_resetting_it(self) -> None:
        entries = [
            "broken json",
            "[]",
            '{"version": 2, "acknowledgments": {}}',
            '{"version": 1, "acknowledgments": []}',
            '{"version": 1, "acknowledgments": {"key": null}}',
            '{"version": 1, "acknowledgments": {"key": {"acknowledged_at": 123}}}',
            '{"version": 1, "acknowledgments": {"key": {"acknowledged_at": "now", "comment_urls": "bad"}}}',
            '{"version": 1, "acknowledgments": {"key": {"acknowledged_at": "now", "comment_urls": [1]}}}',
        ]
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            for content in entries:
                with self.subTest(content=content):
                    state_path.write_text(content)
                    self.run_cli(
                        {},
                        ["--kind", "discussion", "--login", "bramstroker"],
                        expected_error="triage state" if content in entries[:4] else "acknowledgment",
                        state_path=state_path,
                    )
                    self.assertEqual(state_path.read_text(), content)

    def test_failed_state_write_keeps_existing_file(self) -> None:
        responses = {
            ("discussions", None, None): {
                "data": {"repository": {"discussions": create_connection([create_discussion(1)])}}
            },
            ("comments", "d1", None): {"data": {"node": {"comments": create_connection([])}}},
        }
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            original = '{"version": 1, "acknowledgments": {}}\n'
            state_path.write_text(original)
            with patch.object(Path, "replace", side_effect=PermissionError("Cannot save state")):
                self.run_cli(
                    responses,
                    ["--kind", "discussion", "--login", "bramstroker", "--acknowledge", "1"],
                    expected_error="Cannot save state",
                    state_path=state_path,
                )
            self.assertEqual(state_path.read_text(), original)
            self.assertEqual(list(Path(directory).iterdir()), [state_path])
