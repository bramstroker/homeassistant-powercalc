"""Minimal GitHub API client used by the draft entry points.

Standard library only, so the entry points run with a bare ``python3`` on the
runner without any dependency install, exactly like the previous scripts.
"""

from __future__ import annotations

import json
from typing import Any, cast
import urllib.request

API_ROOT = "https://api.github.com"
GRAPHQL_URL = f"{API_ROOT}/graphql"
PAGE_SIZE = 100
COMMIT_LOOKUP_BATCH_SIZE = 50
type JsonObject = dict[str, Any]
type JsonResponse = JsonObject | list[JsonObject] | None


class GitHubClient:
    def __init__(self, token: str, repository: str) -> None:
        self._token = token
        self.repository = repository

    def _request(self, method: str, url: str, payload: JsonObject | None = None) -> JsonResponse:
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

    def _request_list(self, method: str, url: str) -> list[JsonObject]:
        """Request an endpoint that is documented to return an array."""
        response = self._request(method, url)
        return cast(list[JsonObject], response) if response is not None else []

    def _paginate(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            chunk = self._request_list("GET", f"{path}{separator}per_page={PAGE_SIZE}&page={page}")
            items.extend(chunk)
            if len(chunk) < PAGE_SIZE:
                return items
            page += 1

    def merged_pull_requests(self, commit_shas: list[str]) -> list[dict[str, Any]]:
        """Resolve pushed commits to merged pull requests in batched queries."""
        pull_requests: dict[int, dict[str, Any]] = {}
        owner, name = self.repository.split("/", maxsplit=1)
        for offset in range(0, len(commit_shas), COMMIT_LOOKUP_BATCH_SIZE):
            batch = commit_shas[offset : offset + COMMIT_LOOKUP_BATCH_SIZE]
            commit_fields = "\n".join(
                f"""
                commit{index}: object(oid: {json.dumps(sha)}) {{
                  ... on Commit {{
                    associatedPullRequests(first: 10) {{
                      nodes {{
                        number
                        title
                        mergedAt
                        author {{ login }}
                        labels(first: 100) {{ nodes {{ name }} }}
                      }}
                    }}
                  }}
                }}
                """
                for index, sha in enumerate(batch)
            )
            response = self._request(
                "POST",
                GRAPHQL_URL,
                {
                    "query": f"""
                        query($owner: String!, $name: String!) {{
                          repository(owner: $owner, name: $name) {{
                            {commit_fields}
                          }}
                        }}
                    """,
                    "variables": {"owner": owner, "name": name},
                },
            )
            if not isinstance(response, dict):
                raise RuntimeError("GitHub GraphQL commit lookup returned no data")
            if response.get("errors"):
                raise RuntimeError(f"GitHub GraphQL commit lookup failed: {response['errors']}")
            data = response.get("data")
            if not isinstance(data, dict) or not isinstance(repository := data.get("repository"), dict):
                raise RuntimeError("GitHub GraphQL commit lookup returned no repository data")
            for index in range(len(batch)):
                git_object = repository.get(f"commit{index}")
                if not isinstance(git_object, dict):
                    continue
                associated = git_object.get("associatedPullRequests")
                if not isinstance(associated, dict) or not isinstance(nodes := associated.get("nodes"), list):
                    continue
                for node in nodes:
                    if not isinstance(node, dict) or node.get("mergedAt") is None:
                        continue
                    labels = node.get("labels")
                    label_nodes = labels.get("nodes", []) if isinstance(labels, dict) else []
                    author = node.get("author")
                    pull_request = {
                        "number": int(node["number"]),
                        "title": str(node["title"]),
                        "merged_at": node["mergedAt"],
                        "user": {"login": str(author.get("login", "ghost")) if isinstance(author, dict) else "ghost"},
                        "labels": [
                            {"name": str(label["name"])}
                            for label in label_nodes
                            if isinstance(label, dict) and "name" in label
                        ],
                    }
                    pull_requests.setdefault(pull_request["number"], pull_request)
        return [pull_requests[number] for number in sorted(pull_requests)]

    def pull_request_files(self, number: int) -> list[str]:
        files = self.pull_request_file_details(number)
        return [changed_file["filename"] for changed_file in files]

    def pull_request_file_details(self, number: int) -> list[dict[str, Any]]:
        """Return changed files including their GitHub status metadata."""
        return self._paginate(f"/repos/{self.repository}/pulls/{number}/files")

    def commit_sha(self, ref: str) -> str:
        """Resolve a tag, branch or sha to its commit sha."""
        commit = cast(JsonObject, self._request("GET", f"/repos/{self.repository}/commits/{ref}"))
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
            chunk = self._request_list(
                "GET",
                f"/repos/{self.repository}/commits?sha={head_ref}&per_page={PAGE_SIZE}&page={page}",
            )
            if not chunk:
                return shas
            for commit in chunk:
                if commit["sha"] == base_sha:
                    return shas
                shas.append(str(commit["sha"]))
            page += 1

    def releases(self) -> list[dict[str, Any]]:
        return self._paginate(f"/repos/{self.repository}/releases")

    def create_release(self, payload: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("POST", f"/repos/{self.repository}/releases", payload))

    def update_release(self, release_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("PATCH", f"/repos/{self.repository}/releases/{release_id}", payload))

    def delete_release(self, release_id: int) -> None:
        self._request("DELETE", f"/repos/{self.repository}/releases/{release_id}")
