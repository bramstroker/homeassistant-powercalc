# Powercalc measure tooling

This package contains the tooling for measuring lights, speakers, fans, charging devices, average loads, and power time series for Powercalc profiles and analysis.

## Usage

See the [measure documentation](https://docs.powercalc.nl/contributing/measure/) for how to run measurements:

- [Home Assistant app](https://docs.powercalc.nl/contributing/measure/home-assistant-app/) (recommended for Home Assistant OS)
- [CLI - Docker or native Python](https://docs.powercalc.nl/contributing/measure/setup/)

The sections below cover development of the measure tool itself.

## Development setup

**Prerequisites:**
- Python 3.14 or newer.
- Install uv. `curl -LsSf https://astral.sh/uv/install.sh | sh` or see https://github.com/astral-sh/uv

uv manages the virtual environment and installs all dependencies declared by the project:

```
cd utils/measure
uv venv
uv sync --extra dev --extra app --extra cli
```

Start the CLI with:

```
uv run --extra cli python -m measure.measure
```

### Visualize measurement output

Visualization is part of the measure package, while its scientific dependencies are isolated from the normal CLI and Home Assistant app installations:

```bash
uv run --group visualize powercalc-visualize export/LCT010/brightness.csv.gz --output=brightness.png
```

To generate or refresh every supported plot in the profile library:

```bash
uv run --group visualize powercalc-visualize ../../profile_library --force
```

## Developing the Home Assistant app locally

The Home Assistant app has a FastAPI backend (`measure/`) and a Lit frontend (`frontend/`). You can run both locally with hot-reloading of the UI.
See the [measurement tool architecture](../../docs/source/contributing/measure/architecture.md) for the shared CLI/API request, assembly, execution, and result pipeline.

**Prerequisites:**
- A reachable Home Assistant instance and a long-lived access token (HA → profile → Security → *Long-lived access tokens*). The app proxies real HA entity data, so `/api/entities` needs a live instance.
- Python/uv set up as described under [Development setup](#development-setup), and Node.js for the frontend.

**Terminal 1 — backend** (from `utils/measure`):
```
uv run --extra app python -m measure.ha_app.main \
  --host 127.0.0.1 --port 8099 \
  --data-root .dev-data \
  --hass-url ws://127.0.0.1:8123/api/websocket \
  --hass-token <LONG_LIVED_TOKEN>
```
Use the full Home Assistant WebSocket endpoint: `ws://<host>:8123/api/websocket` for a direct connection, or `ws://supervisor/core/websocket` from a Home Assistant add-on. `--hass-token` may be omitted if `SUPERVISOR_TOKEN` is exported instead. Session state and settings are written to `--data-root` (here `.dev-data`).

GitHub device login requires a GitHub OAuth App with Device Flow enabled. Set its public client ID in `POWERCALC_GITHUB_CLIENT_ID` before starting the backend. Device login requests `public_repo` and `workflow`; the latter is needed to base a clean contribution branch on an upstream commit when the user's fork has stale workflow files. Without a client ID, the UI disables device login and retains the personal-access-token fallback.

Automatic contributions target `bramstroker/homeassistant-powercalc` on `master` by default. For an isolated test repository, set `POWERCALC_GITHUB_REPOSITORY=owner/repository` and, when needed, `POWERCALC_GITHUB_BRANCH=main` before starting the backend. Both preview validation and pull-request submission use this target.

**Terminal 2 — frontend** (from `utils/measure/frontend`):
```
npm install
npm run dev
```
Open http://localhost:5173. The Vite dev server proxies `/api` (including the SSE event stream) to the backend on port 8099, mirroring the single-origin ingress deployment.

To run the app the way it ships (single origin, no hot-reload), build the frontend with `npm run build` and start the backend with `create_app(..., static_root=Path("frontend/dist"))`; the UI is then served by FastAPI on port 8099.

### Checks

```
# backend (from utils/measure)
uv run ruff check measure/ tests/
uv run pytest

# frontend (from utils/measure/frontend)
npm run typecheck
npm test
```

## Building and running docker image locally
```
docker build -t measure .
docker run --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it measure
```
