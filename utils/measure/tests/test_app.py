from __future__ import annotations

import json
import logging
from pathlib import Path

from measure.app import _configure_logging, _read_options


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
