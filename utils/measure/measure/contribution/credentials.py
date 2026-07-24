from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from measure.contribution.files import write_json_atomic

CredentialKind = Literal["oauth", "pat"]


@dataclass(frozen=True)
class StoredCredential:
    kind: CredentialKind
    token: str
    github_username: str | None = None
    scopes: tuple[str, ...] = ()
    permissions_verified: bool = False


class CredentialStore:
    """Persist private GitHub credentials without exposing them through public models."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> StoredCredential | None:
        if not self.path.exists():
            return None
        with self.path.open(encoding="utf-8") as file:
            value = json.load(file)
        if not isinstance(value, dict):
            raise ValueError("Credential file must contain an object")
        token = value.get("token")
        kind = value.get("kind")
        username = value.get("github_username")
        scopes = value.get("scopes", [])
        permissions_verified = value.get("permissions_verified", False)
        if kind not in {"oauth", "pat"} or not isinstance(token, str) or not token:
            raise ValueError("Credential file is invalid")
        if username is not None and not isinstance(username, str):
            raise ValueError("Credential username is invalid")
        if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
            raise ValueError("Credential scopes are invalid")
        if not isinstance(permissions_verified, bool):
            raise ValueError("Credential permission status is invalid")
        return StoredCredential(
            kind=kind,
            token=token,
            github_username=username,
            scopes=tuple(scopes),
            permissions_verified=permissions_verified,
        )

    def save(self, credential: StoredCredential) -> None:
        write_json_atomic(
            self.path,
            {
                "kind": credential.kind,
                "token": credential.token,
                "github_username": credential.github_username,
                "scopes": list(credential.scopes),
                "permissions_verified": credential.permissions_verified,
            },
            private=True,
        )

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
