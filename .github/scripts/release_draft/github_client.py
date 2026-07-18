"""Minimal GitHub REST client used by the draft entry points.

Standard library only, so the entry points run with a bare ``python3`` on the
runner without any dependency install, exactly like the previous scripts.
"""

from __future__ import annotations

import json
from typing import Any, cast
import urllib.request

API_ROOT = "https://api.github.com"
PAGE_SIZE = 100


class GitHubClient:
    def __init__(self, token: str, repository: str) -> None:
        self._token = token
        self.repository = repository

    def _request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        if url.startswith("/"):
            url = f"{API_ROOT}{url}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(  # noqa: S310 - fixed https API root
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request) as response:  # noqa: S310
            body = response.read()
        return json.loads(body) if body else None

    def _paginate(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            chunk = self._request("GET", f"{path}{separator}per_page={PAGE_SIZE}&page={page}")
            items.extend(chunk)
            if len(chunk) < PAGE_SIZE:
                return items
            page += 1

    def merged_pull_requests(self, commit_shas: list[str]) -> list[dict[str, Any]]:
        """Resolve pushed commits to the merged pull requests they belong to."""
        pull_requests: dict[int, dict[str, Any]] = {}
        for sha in commit_shas:
            for pull_request in self._request("GET", f"/repos/{self.repository}/commits/{sha}/pulls"):
                if pull_request.get("merged_at") is not None:
                    pull_requests.setdefault(pull_request["number"], pull_request)
        return [pull_requests[number] for number in sorted(pull_requests)]

    def pull_request_files(self, number: int) -> list[str]:
        files = self._paginate(f"/repos/{self.repository}/pulls/{number}/files")
        return [changed_file["filename"] for changed_file in files]

    def commit_sha(self, ref: str) -> str:
        """Resolve a tag, branch or sha to its commit sha."""
        commit = self._request("GET", f"/repos/{self.repository}/commits/{ref}")
        return str(commit["sha"])

    def commit_shas_since(self, base_sha: str | None, head_ref: str) -> list[str]:
        """List commit shas on ``head_ref`` newer than ``base_sha``.

        Walks the branch history from the tip until it reaches ``base_sha``,
        which avoids the 250-commit cap of the compare endpoint. When
        ``base_sha`` is ``None`` the whole history is returned.
        """
        shas: list[str] = []
        page = 1
        while True:
            chunk = self._request(
                "GET",
                f"/repos/{self.repository}/commits?sha={head_ref}&per_page={PAGE_SIZE}&page={page}",
            )
            if not chunk:
                return shas
            for commit in chunk:
                if commit["sha"] == base_sha:
                    return shas
                shas.append(commit["sha"])
            page += 1

    def releases(self) -> list[dict[str, Any]]:
        return self._paginate(f"/repos/{self.repository}/releases")

    def create_release(self, payload: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("POST", f"/repos/{self.repository}/releases", payload))

    def update_release(self, release_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("PATCH", f"/repos/{self.repository}/releases/{release_id}", payload))

    def delete_release(self, release_id: int) -> None:
        self._request("DELETE", f"/repos/{self.repository}/releases/{release_id}")
