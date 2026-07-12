from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import uvicorn

from measure.api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Powercalc Measure Home Assistant app")
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--data-root", type=Path, default=Path("/data"))
    args = parser.parse_args()
    options = _read_options(args.data_root)
    debug = bool(options.get("debug_logging", False))
    _configure_logging(debug)
    app = create_app(
        data_root=args.data_root,
        use_dummy_power_meter=bool(options.get("dummy_power_meter", False)),
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        workers=1,
        proxy_headers=False,
        log_level="debug" if debug else "info",
    )


def _read_options(data_root: Path) -> dict[str, object]:
    """Read the add-on options written to ``options.json`` by the Home Assistant supervisor."""
    try:
        options = json.loads((data_root / "options.json").read_text())
    except (OSError, ValueError):
        return {}
    return options if isinstance(options, dict) else {}


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("measure").setLevel(level)


if __name__ == "__main__":
    main()
