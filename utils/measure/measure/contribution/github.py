from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
import os
import re
import time
from typing import Any, Protocol

import requests

UPSTREAM_OWNER = "bramstroker"
UPSTREAM_REPO = "homeassistant-powercalc"
UPSTREAM_BRANCH = "master"
UPSTREAM_REPOSITORY_ENV = "POWERCALC_GITHUB_REPOSITORY"
UPSTREAM_BRANCH_ENV = "POWERCALC_GITHUB_BRANCH"
API_BASE_URL = "https://api.github.com"
GITHUB_LOGIN_URL = "https://github.com"
REQUIRED_OAUTH_SCOPES = ("public_repo", "workflow")


class GitHubResponse(Protocol):
    status_code: int
    headers: Mapping[str, str]

    def json(self) -> object: ...


class GitHubTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: object | None = None,
        params: Mapping[str, str] | None = None,
        timeout: int = 30,
    ) -> GitHubResponse: ...


@dataclass(frozen=True)
class GitHubUser:
    login: str
    name: str | None = None
    email: str | None = None
    scopes: tuple[str, ...] = ()
    scopes_reported: bool = False


@dataclass(frozen=True)
class GitHubRepository:
    owner: str = UPSTREAM_OWNER
    name: str = UPSTREAM_REPO
    branch: str = UPSTREAM_BRANCH

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> GitHubRepository:
        values = os.environ if environ is None else environ
        full_name = values.get(UPSTREAM_REPOSITORY_ENV, f"{UPSTREAM_OWNER}/{UPSTREAM_REPO}").strip()
        parts = full_name.split("/")
        if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
            raise ValueError(f"{UPSTREAM_REPOSITORY_ENV} must use the owner/repository format")
        branch = values.get(UPSTREAM_BRANCH_ENV, UPSTREAM_BRANCH).strip()
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch)
            or ".." in branch
            or "//" in branch
            or branch.endswith("/")
        ):
            raise ValueError(f"{UPSTREAM_BRANCH_ENV} contains an invalid branch name")
        return cls(owner=parts[0], name=parts[1], branch=branch)


class GitHubClient:
    """Small GitHub REST client with injectable transport for deterministic tests."""

    def __init__(
        self,
        token: str | None = None,
        *,
        transport: GitHubTransport | None = None,
        api_base_url: str = API_BASE_URL,
        login_url: str = GITHUB_LOGIN_URL,
        repository: GitHubRepository | None = None,
    ) -> None:
        self.token = token
        self.transport = transport or requests
        self.api_base_url = api_base_url.rstrip("/")
        self.login_url = login_url.rstrip("/")
        self.repository = repository or GitHubRepository.from_environment()

    def start_device_flow(self, client_id: str, scopes: tuple[str, ...]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.login_url}/login/device/code",
            json={"client_id": client_id, "scope": " ".join(scopes)},
            authenticated=False,
            accept_json=True,
        )

    def poll_device_flow(self, client_id: str, device_code: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.login_url}/login/oauth/access_token",
            json={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            authenticated=False,
            accept_json=True,
        )

    def validate_user(self) -> GitHubUser:
        response = self._raw("GET", f"{self.api_base_url}/user")
        data = self._decode_response(response)
        headers = response.headers
        scope_header = headers.get("X-OAuth-Scopes", "")
        scopes = tuple(scope.strip() for scope in scope_header.split(",") if scope.strip())
        return GitHubUser(
            login=str(data["login"]),
            name=data.get("name"),
            email=data.get("email"),
            scopes=scopes,
            scopes_reported="X-OAuth-Scopes" in headers,
        )

    def get_repository(self, owner: str, repo: str) -> dict[str, Any] | None:
        response = self._raw("GET", f"{self.api_base_url}/repos/{owner}/{repo}")
        if response.status_code == 404:
            return None
        return self._decode_response(response)

    def find_fork(self, username: str, repo: str | None = None) -> dict[str, Any] | None:
        repo = repo or self.repository.name
        repository = self.get_repository(username, repo)
        if repository is None or not bool(repository.get("fork")):
            return None
        parent = repository.get("parent")
        if isinstance(parent, dict) and parent.get("full_name") == self.repository.full_name:
            return repository
        return None

    def create_fork(self, *, poll_attempts: int = 60, poll_interval: float = 2.0) -> dict[str, Any]:
        self._request("POST", f"{self.api_base_url}/repos/{self.repository.full_name}/forks")
        user = self.validate_user()
        for _ in range(poll_attempts):
            repository = self.find_fork(user.login)
            if (
                repository is not None
                and self.get_ref(
                    str(repository["owner"]["login"]),
                    str(repository["name"]),
                    self.repository.branch,
                )
                is not None
            ):
                return repository
            time.sleep(poll_interval)
        raise GitHubApiError("GitHub fork was not available after polling")

    def get_file(self, owner: str, repo: str, path: str, ref: str) -> bytes:
        data = self._request(
            "GET",
            f"{self.api_base_url}/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
        )
        if data.get("encoding") == "base64" and isinstance(data.get("content"), str) and data["content"].strip():
            return self._decode_base64(data["content"], path)
        # Files above 1 MB are not inlined by the contents API (encoding "none");
        # fetch them through the blob API instead, which supports up to 100 MB.
        blob_sha = data.get("sha")
        if not isinstance(blob_sha, str) or not blob_sha:
            raise GitHubApiError(f"GitHub did not return content or a blob sha for {path}")
        blob = self._request("GET", f"{self.api_base_url}/repos/{owner}/{repo}/git/blobs/{blob_sha}")
        if blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
            raise GitHubApiError(f"GitHub did not return base64 content for {path}")
        return self._decode_base64(blob["content"], path)

    @staticmethod
    def _decode_base64(content: str, path: str) -> bytes:
        try:
            return base64.b64decode(content, validate=False)
        except ValueError as error:
            raise GitHubApiError(f"GitHub returned invalid base64 content for {path}") from error

    def get_ref(self, owner: str, repo: str, branch: str) -> dict[str, Any] | None:
        response = self._raw("GET", f"{self.api_base_url}/repos/{owner}/{repo}/git/ref/heads/{branch}")
        if response.status_code == 404:
            return None
        return self._decode_response(response)

    def get_commit(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        return self._request("GET", f"{self.api_base_url}/repos/{owner}/{repo}/git/commits/{sha}")

    def sync_fork_branch(self, owner: str, repo: str, branch: str) -> None:
        """Fetch upstream objects into a fork through an isolated contribution branch.

        GitHub can report merge conflicts for a divergent fork while still fetching
        the upstream objects. The coordinator creates its commit directly on the
        upstream parent, so the merge result itself is intentionally discarded.
        """
        response = self._raw(
            "POST",
            f"{self.api_base_url}/repos/{owner}/{repo}/merge-upstream",
            json={"branch": branch},
        )
        if response.status_code == 409:
            try:
                data = response.json()
            except ValueError as error:
                raise GitHubApiError("GitHub returned invalid JSON while fetching the upstream branch") from error
            message = data.get("message") if isinstance(data, dict) else None
            if message == "There are merge conflicts":
                return
        try:
            self._decode_response(response)
        except GitHubApiError as error:
            raise GitHubApiError(
                f"GitHub could not fetch upstream into contribution branch {branch}: {error}",
            ) from error

    def create_ref(self, owner: str, repo: str, branch: str, sha: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.api_base_url}/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )

    def update_ref(self, owner: str, repo: str, branch: str, sha: str, *, force: bool = False) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"{self.api_base_url}/repos/{owner}/{repo}/git/refs/heads/{branch}",
            json={"sha": sha, "force": force},
        )

    def create_blob(self, owner: str, repo: str, content: str, *, encoding: str = "base64") -> str:
        data = self._request(
            "POST",
            f"{self.api_base_url}/repos/{owner}/{repo}/git/blobs",
            json={"content": content, "encoding": encoding},
        )
        return str(data["sha"])

    def create_tree(self, owner: str, repo: str, base_tree: str, tree: tuple[dict[str, Any], ...]) -> str:
        data = self._request(
            "POST",
            f"{self.api_base_url}/repos/{owner}/{repo}/git/trees",
            json={"base_tree": base_tree, "tree": list(tree)},
        )
        return str(data["sha"])

    def create_commit(self, owner: str, repo: str, message: str, tree_sha: str, parent_sha: str) -> str:
        data = self._request(
            "POST",
            f"{self.api_base_url}/repos/{owner}/{repo}/git/commits",
            json={"message": message, "tree": tree_sha, "parents": [parent_sha]},
        )
        return str(data["sha"])

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self.api_base_url}/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "head": head,
                "base": base,
                "body": body,
                "draft": False,
                "maintainer_can_modify": True,
            },
        )

    def find_pull_request(self, owner: str, repo: str, *, head: str, base: str) -> dict[str, Any] | None:
        response = self._raw(
            "GET",
            f"{self.api_base_url}/repos/{owner}/{repo}/pulls",
            params={"state": "open", "head": head, "base": base},
        )
        data = self._decode_list(response)
        return next((item for item in data if isinstance(item, dict)), None)

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: object | None = None,
        params: Mapping[str, str] | None = None,
        authenticated: bool = True,
        accept_json: bool = False,
    ) -> dict[str, Any]:
        response = self._raw(
            method,
            url,
            json=json,
            params=params,
            authenticated=authenticated,
            accept_json=accept_json,
        )
        return self._decode_response(response)

    def _raw(
        self,
        method: str,
        url: str,
        *,
        json: object | None = None,
        params: Mapping[str, str] | None = None,
        authenticated: bool = True,
        accept_json: bool = False,
    ) -> GitHubResponse:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if accept_json:
            headers["Accept"] = "application/json"
        if authenticated:
            if not self.token:
                raise GitHubApiError("GitHub token is required")
            headers["Authorization"] = f"Bearer {self.token}"
        return self.transport.request(method, url, headers=headers, json=json, params=params, timeout=30)

    @classmethod
    def _decode_response(cls, response: GitHubResponse) -> dict[str, Any]:
        data = cls._decode_json(response)
        if not isinstance(data, dict):
            raise GitHubApiError("GitHub response must be an object")
        return data

    @classmethod
    def _decode_list(cls, response: GitHubResponse) -> list[Any]:
        data = cls._decode_json(response)
        if not isinstance(data, list):
            raise GitHubApiError("GitHub response must be a list")
        return data

    @staticmethod
    def _decode_json(response: GitHubResponse) -> object:
        try:
            data = response.json()
        except ValueError as error:
            raise GitHubApiError(f"GitHub returned invalid JSON with status {response.status_code}") from error
        if not 200 <= response.status_code < 300:
            message = data.get("message") if isinstance(data, dict) else None
            raise GitHubApiError(str(message or f"GitHub request failed with status {response.status_code}"))
        return data


class GitHubApiError(RuntimeError):
    pass
