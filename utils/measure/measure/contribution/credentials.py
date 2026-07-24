from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Literal

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
        self._write_private_json(
            {
                "kind": credential.kind,
                "token": credential.token,
                "github_username": credential.github_username,
                "scopes": list(credential.scopes),
                "permissions_verified": credential.permissions_verified,
            },
        )

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

    def _write_private_json(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.unlink(missing_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(value, file, indent=2, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary, 0o600)
            temporary.replace(self.path)
            os.chmod(self.path, 0o600)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
