import json
import os
from pathlib import Path

from measure.contribution.credentials import CredentialKind, CredentialStore, StoredCredential
import pytest


@pytest.mark.parametrize("kind", list(CredentialKind))
def test_credential_store_persists_private_file_without_public_model_serialization(
    tmp_path: Path,
    kind: CredentialKind,
) -> None:
    path = tmp_path / "github.json"
    store = CredentialStore(path)
    credential_value = "secret-token"

    store.save(StoredCredential(kind=kind, token=credential_value, github_username="octo"))

    assert stat_mode(path) == 0o600
    assert json.loads(path.read_text())["kind"] == kind.value
    loaded = store.load()
    assert loaded == StoredCredential(kind=kind, token=credential_value, github_username="octo")
    assert loaded.kind is kind


@pytest.mark.parametrize("kind", ["invalid", None, 42, [], {}])
def test_credential_store_rejects_invalid_kind(tmp_path: Path, kind: object) -> None:
    path = tmp_path / "github.json"
    path.write_text(json.dumps({"kind": kind, "token": "test-token"}))

    with pytest.raises(ValueError, match="Credential file is invalid"):
        CredentialStore(path).load()


def test_credential_store_clear_removes_credentials(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "github.json")
    credential_value = "ghp_secret"
    store.save(StoredCredential(kind=CredentialKind.PAT, token=credential_value))

    store.clear()

    assert store.load() is None


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777
