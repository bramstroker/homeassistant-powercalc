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


@pytest.mark.parametrize("value", [None, [], "token", 42])
def test_credential_store_rejects_non_object_file(tmp_path: Path, value: object) -> None:
    path = tmp_path / "github.json"
    path.write_text(json.dumps(value))

    with pytest.raises(ValueError, match="Credential file must contain an object"):
        CredentialStore(path).load()


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("token", "", "Credential file is invalid"),
        ("token", None, "Credential file is invalid"),
        ("token", 42, "Credential file is invalid"),
        ("github_username", 42, "Credential username is invalid"),
        ("scopes", "repo", "Credential scopes are invalid"),
        ("scopes", ["repo", 42], "Credential scopes are invalid"),
        ("permissions_verified", "true", "Credential permission status is invalid"),
        ("permissions_verified", 1, "Credential permission status is invalid"),
    ],
)
def test_credential_store_rejects_invalid_fields(tmp_path: Path, field: str, value: object, message: str) -> None:
    path = tmp_path / "github.json"
    path.write_text(json.dumps({"kind": "pat", "token": "test-token", field: value}))

    with pytest.raises(ValueError, match=message):
        CredentialStore(path).load()


def test_credential_store_preserves_verified_permissions_and_scopes(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "github.json")
    credential = StoredCredential(
        kind=CredentialKind.OAUTH,
        token="test-token",  # noqa: S106
        github_username="octo",
        scopes=("repo", "read:user"),
        permissions_verified=True,
    )

    store.save(credential)

    assert store.load() == credential


def test_credential_store_loads_legacy_file_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "github.json"
    path.write_text(json.dumps({"kind": "pat", "token": "test-token"}))

    assert CredentialStore(path).load() == StoredCredential(kind=CredentialKind.PAT, token="test-token")  # noqa: S106


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777
