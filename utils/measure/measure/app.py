from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from measure.api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Powercalc Measure Home Assistant app")
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--data-root", type=Path, default=Path("/data"))
    args = parser.parse_args()
    app = create_app(data_root=args.data_root)
    uvicorn.run(app, host=args.host, port=args.port, workers=1, proxy_headers=False)


if __name__ == "__main__":
    main()
