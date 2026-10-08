from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from tests.ha_app.api_test_support import AppClientFactory


@pytest.fixture
def app_client_factory(tmp_path: Path) -> Iterator[AppClientFactory]:
    factory = AppClientFactory(tmp_path)
    yield factory
    factory.close()


@pytest.fixture
def app_client(app_client_factory: AppClientFactory) -> TestClient:
    return app_client_factory()
