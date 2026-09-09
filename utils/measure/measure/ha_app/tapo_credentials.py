from dataclasses import dataclass
import json
from pathlib import Path

from measure.files import write_json_atomic


@dataclass(frozen=True)
class TapoCredentials:
    """TP-Link account credentials used to authenticate a Tapo power meter."""

    username: str
    password: str


class TapoCredentialStore:
    """Persist Tapo credentials without exposing them through app settings."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> TapoCredentials | None:
        if not self.path.exists():
            return None
        with self.path.open(encoding="utf-8") as file:
            value = json.load(file)
        username = value.get("username") if isinstance(value, dict) else None
        password = value.get("password") if isinstance(value, dict) else None
        if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
            raise ValueError("Tapo credential file is invalid")
        return TapoCredentials(username=username, password=password)

    def save(self, credentials: TapoCredentials) -> None:
        write_json_atomic(self.path, {"username": credentials.username, "password": credentials.password}, private=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
