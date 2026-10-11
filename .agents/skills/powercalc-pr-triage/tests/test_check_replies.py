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


class CheckRepliesTest(unittest.TestCase):
    def run_cli(self, responses: dict, arguments: list[str] | None = None) -> dict:
        stdout = StringIO()
        stderr = StringIO()

        def run_gh(command: list[str], **options: object) -> subprocess.CompletedProcess:
            endpoint = command[4]
            response = responses[endpoint]
            self.assertEqual(command[:4], ["gh", "api", "--method", "GET"])
            self.assertEqual(options, {"check": True, "capture_output": True, "text": True})
            if isinstance(response, list):
                self.assertEqual(command[5:], ["--paginate", "--slurp"])
            else:
                self.assertEqual(command[5:], [])
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(response), stderr="")

        with (
            patch.object(sys, "argv", [str(SCRIPT), *(arguments or [])]),
            patch("subprocess.run", side_effect=run_gh),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as result,
        ):
            runpy.run_path(str(SCRIPT), run_name="__main__")
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
            }
            for number in range(1, 6)
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

        report = self.run_cli(responses)
        self.assertEqual(report["total_prs"], 5)
        self.assertEqual(report["login"], "BRAMSTROKER")
        self.assertEqual(report["repository"], REPO)
        self.assertEqual(report["label"], "waiting-for-author")
        self.assertEqual(
            report["counts"],
            {"new_human_comments": 2, "bot_only": 1, "no_new_comments": 1, "no_baseline": 1},
        )
        first, bot_only, same_time, no_baseline, reviews = report["pull_requests"]
        self.assertEqual([comment["kind"] for comment in first["new_comments"]], ["discussion", "inline_review"])
        self.assertEqual([comment["author"] for comment in bot_only["new_comments"]], ["automation", "ci[bot]"])
        self.assertEqual(same_time["new_comments"], [])
        self.assertIsNone(no_baseline["latest_user_comment"])
        self.assertEqual(no_baseline["new_comments"], [])
        self.assertEqual(reviews["latest_user_comment"]["created_at"], "2026-10-03T12:00:00Z")
        self.assertEqual([comment["author"] for comment in reviews["new_comments"]], ["contributor", "[deleted]"])
        self.assertEqual(reviews["new_comments"][0]["body"], "Comment from contributor")
        self.assertIn("#comment-contributor-4", reviews["new_comments"][0]["url"])

    def test_overrides_and_empty_repository(self) -> None:
        report = self.run_cli(
            {
                "repos/example/repo/labels/needs%20reply": {},
                "repos/example/repo/issues?state=open&labels=needs+reply&per_page=100": [[]],
            },
            ["--repo", "example/repo", "--label", "needs reply", "--login", "someone"],
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
        report = namespace["summarize_pr"]({"number": 1, "title": "Profile", "html_url": "pr"}, comments, "bramstroker")
        self.assertEqual(report["status"], "no_new_comments")
        self.assertEqual(report["latest_user_comment"]["kind"], "review")
        self.assertEqual(report["new_comments"], [])
