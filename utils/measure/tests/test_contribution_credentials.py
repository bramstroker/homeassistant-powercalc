from __future__ import annotations

import os
from pathlib import Path

from measure.contribution.credentials import CredentialStore, StoredCredential


def test_credential_store_persists_private_file_without_public_model_serialization(tmp_path: Path) -> None:
    path = tmp_path / "github.json"
    store = CredentialStore(path)
    credential_value = "secret-token"

    store.save(StoredCredential(kind="oauth", token=credential_value, github_username="octo"))

    assert stat_mode(path) == 0o600
    assert store.load() == StoredCredential(kind="oauth", token=credential_value, github_username="octo")


def test_credential_store_clear_removes_credentials(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "github.json")
    credential_value = "ghp_secret"
    store.save(StoredCredential(kind="pat", token=credential_value))

    store.clear()

    assert store.load() is None


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777
