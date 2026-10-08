import json
import logging
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import ANY, patch

from measure.ha_app.main import _configure_logging, _HealthCheckAccessFilter, _read_options, main
import pytest


@pytest.mark.parametrize(
    "arguments,setting,host,ingress_only",
    [
        ([], None, "127.0.0.1", True),
        (["--developer-mode"], None, "127.0.0.1", True),
        (["--allow-local-access"], None, "127.0.0.1", False),
        (["--allow-local-access", "--host", "::1"], None, "::1", False),
        ([], "false", "127.0.0.1", False),
        (["--host", "0.0.0.0"], "true", "0.0.0.0", True),  # noqa: S104
        (["--host", "0.0.0.0"], None, "0.0.0.0", True),  # noqa: S104
        (["--host", "0.0.0.0"], "invalid", "0.0.0.0", True),  # noqa: S104
    ],
)
def test_main_access_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    setting: str | None,
    host: str,
    ingress_only: bool,
) -> None:
    if setting is None:
        monkeypatch.delenv("MEASURE_TRUSTED_INGRESS_ONLY", raising=False)
    else:
        monkeypatch.setenv("MEASURE_TRUSTED_INGRESS_ONLY", setting)
    monkeypatch.setattr("sys.argv", ["measure-app", "--data-root", str(tmp_path), *arguments])
    with patch("measure.ha_app.main.create_app") as create_app, patch("measure.ha_app.main.uvicorn.run") as run:
        main()

    assert create_app.call_args.kwargs["trusted_ingress_only"] is ingress_only
    run.assert_called_once_with(
        create_app.return_value,
        host=host,
        port=8099,
        workers=1,
        proxy_headers=False,
        log_level="info",
        log_config=ANY,
    )
    assert run.call_args.kwargs["log_config"] is not None


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.0.2.1", "localhost", "example.com"])  # noqa: S104
@pytest.mark.parametrize("use_environment", [False, True])
def test_main_rejects_external_local_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    host: str,
    use_environment: bool,
) -> None:
    monkeypatch.setenv("MEASURE_TRUSTED_INGRESS_ONLY", "false" if use_environment else "true")
    arguments = ["measure-app", "--data-root", str(tmp_path), "--host", host]
    if not use_environment:
        arguments.append("--allow-local-access")
    monkeypatch.setattr("sys.argv", arguments)
    with (
        patch("measure.ha_app.main.create_app") as create_app,
        patch("measure.ha_app.main.uvicorn.run") as run,
        pytest.raises(SystemExit) as error,
    ):
        main()

    assert error.value.code == 2
    assert "Local access requires a loopback IP address" in capsys.readouterr().err
    create_app.assert_not_called()
    run.assert_not_called()


def test_read_options_empty_when_missing(tmp_path: Path) -> None:
    assert _read_options(tmp_path) == {}


def test_read_options_empty_when_invalid(tmp_path: Path) -> None:
    (tmp_path / "options.json").write_text("not json")
    assert _read_options(tmp_path) == {}

    (tmp_path / "options.json").write_text(json.dumps([1, 2, 3]))
    assert _read_options(tmp_path) == {}


def test_read_options_returns_option_values(tmp_path: Path) -> None:
    (tmp_path / "options.json").write_text(json.dumps({"debug_logging": True, "dummy_power_meter": True}))
    options = _read_options(tmp_path)
    assert options["debug_logging"] is True
    assert options["dummy_power_meter"] is True


def test_configure_logging_sets_measure_level() -> None:
    logger = logging.getLogger("measure")
    original = logger.level
    try:
        _configure_logging(debug=True)
        assert logger.level == logging.DEBUG
        _configure_logging(debug=False)
        assert logger.level == logging.INFO
    finally:
        logger.setLevel(original)


@pytest.mark.parametrize("debug", [False, True])
def test_server_log_output(debug: bool) -> None:
    # Run logging configuration in isolation: dictConfig closes existing handlers,
    # including pytest's capture handlers if called in the test process.
    result = subprocess.run(  # noqa: S603 - fixed script executed with the test interpreter
        [
            sys.executable,
            "-c",
            """
import logging
import sys
from unittest.mock import patch

import uvicorn
from measure.ha_app.main import main

debug = sys.argv[1] == "True"
sys.argv = ["measure-app"]

def run(app, **kwargs):
    uvicorn.Config(app, **kwargs)
    logging.getLogger("measure").info("Measurement ready")
    server = logging.getLogger("uvicorn.error")
    server.info("Application startup complete")
    server.error("Server error")
    server.debug("Server debug details")
    access = logging.getLogger("uvicorn.access")
    for path, status in [("/health", 200), ("/health", 503), ("/api/sessions", 200)]:
        access.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:1234", "GET", path, "1.1", status)
    server.info("Application shutdown complete")

with (
    patch("measure.ha_app.main._read_options", return_value={"debug_logging": debug}),
    patch("measure.ha_app.main.create_app"),
    patch("measure.ha_app.main.uvicorn.run", side_effect=run),
):
    main()
""",
            str(debug),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    output = result.stdout + result.stderr
    assert '"GET /health HTTP/1.1" 200' not in output
    assert '"GET /health HTTP/1.1" 503' in output
    assert '"GET /api/sessions HTTP/1.1" 200' in output
    assert "Measurement ready" in output
    assert "Application startup complete" in output
    assert "Application shutdown complete" in output
    assert "Server error" in output
    assert ("Server debug details" in output) is debug
    for line in output.splitlines():
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ", line)


@pytest.mark.parametrize(
    "method,path,status,visible",
    [
        ("GET", "/health", 200, False),
        ("GET", "/health", 204, False),
        ("GET", "/health", 299, False),
        ("GET", "/health", 199, True),
        ("GET", "/health", 301, True),
        ("GET", "/health", 403, True),
        ("GET", "/health", 500, True),
        ("POST", "/health", 200, True),
        ("GET", "/api/sessions", 200, True),
        ("GET", "/health/details", 200, True),
        ("GET", "/health", "unknown", True),
    ],
)
def test_health_check_access_filter(method: str, path: str, status: int | str, visible: bool) -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        "%s %s %s %s %s",
        ("127.0.0.1:1234", method, path, "1.1", status),
        None,
    )
    assert _HealthCheckAccessFilter().filter(record) is visible


@pytest.mark.parametrize("args", [(), ("detail",), {"detail": "value"}])
def test_health_check_access_filter_keeps_other_records(args: tuple[object, ...] | dict[str, object]) -> None:
    record = logging.makeLogRecord({"msg": "Other access message", "args": args})
    assert _HealthCheckAccessFilter().filter(record) is True
