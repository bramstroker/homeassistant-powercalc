"""Tests for the supporters release-note footer."""

from __future__ import annotations

from types import TracebackType
from typing import Self
import urllib.request

import pytest
import supporters


class Response:
    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self) -> bytes:
        return b'[{"name": "Alice", "coffees": 1}]'


def test_fetch_supporters_identifies_the_release_drafter(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_request: urllib.request.Request | None = None

    def urlopen(request: urllib.request.Request, timeout: int) -> Response:
        nonlocal captured_request
        captured_request = request
        assert timeout == 10
        return Response()

    monkeypatch.setattr(supporters.urllib.request, "urlopen", urlopen)

    assert supporters.fetch_supporters() == [{"name": "Alice", "coffees": 1}]
    assert captured_request is not None
    assert captured_request.get_header("User-agent") == supporters.USER_AGENT
    assert captured_request.get_header("Accept") == "application/json"
