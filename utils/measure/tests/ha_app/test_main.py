import json
import logging
from pathlib import Path
from unittest.mock import patch

from measure.ha_app.main import _configure_logging, _read_options, main
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
    )


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
