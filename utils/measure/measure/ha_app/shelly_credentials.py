from dataclasses import dataclass
import json
from pathlib import Path

from measure.contribution.files import write_json_atomic


@dataclass(frozen=True)
class ShellyCredentials:
    """Credentials used for an authenticated Shelly power meter."""

    password: str


class ShellyCredentialStore:
    """Persist Shelly credentials without exposing them through app settings."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> ShellyCredentials | None:
        if not self.path.exists():
            return None
        with self.path.open(encoding="utf-8") as file:
            value = json.load(file)
        password = value.get("password") if isinstance(value, dict) else None
        if not isinstance(password, str) or not password:
            raise ValueError("Shelly credential file is invalid")
        return ShellyCredentials(password=password)

    def save(self, credentials: ShellyCredentials) -> None:
        write_json_atomic(self.path, {"password": credentials.password}, private=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
