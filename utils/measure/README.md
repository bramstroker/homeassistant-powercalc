# Powercalc measure tooling

This package contains everything you need to automatically take measurements of lights to contribute to this repository.

## Setup

There are three ways to run the measure tool: as an experimental Home Assistant app, using Docker, or natively using Python.
Home Assistant OS users can use the app; for other installations, Docker is recommended because it bundles the required dependencies.

### Home Assistant app (experimental)

Home Assistant OS users can run light measurements from an ingress UI without creating a long-lived access token. The first release supports Home Assistant light entities and Home Assistant power sensors, with an optional voltage sensor. It does not yet support the direct device controllers, OCR, speakers, fans, charging, or other CLI runners.

See the [Home Assistant app guide](https://docs.powercalc.nl/contributing/measure/home-assistant-app/) for availability, installation, safety notes, storage, and troubleshooting. The existing Docker and native workflows remain fully supported.

### Docker

**Prerequisites:**
- Install docker engine, see https://docs.docker.com/get-docker/
- Start up the command line and verify docker is running: `docker version`
- Create a new directory. for example `powercalc-measure`
- Go to this directory and copy the `.env.dist` file from [here](https://github.com/bramstroker/homeassistant-powercalc/blob/master/utils/measure/.env.dist) into the directory and rename it to `.env`.
- Modify the `.env` file to your needs. Selecting the `POWER_METER` and `LIGHT_CONTROLLER` here is mandatory

#### Start measurements

Go to the directory you created in a command line.

##### Linux and MacOS
```
docker run --pull=always --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it bramgerritsen/powercalc-measure:latest
```
##### Windows
```
docker run --pull=always --rm --name=measure --env-file=.env -v %CD%/export:/app/export -v %CD%/.persistent:/app/.persistent -it bramgerritsen/powercalc-measure:latest
```
Note: if you use PowerShell instead of the Windows command line tool, you must use the full paths instead of relative paths.

The script will ask you a few questions, then proceed taking measurements.

After the measurements are finished you will find the files in `export` directory.

### Native

Use this installation method when the docker method is not working for you or you want to do any development on the script.

**Prerequisites:**
- Make sure you have Python 3 running on your system. Version 3.14 is recommended.
- Install uv. `curl -LsSf https://astral.sh/uv/install.sh | sh` or see https://github.com/astral-sh/uv

uv manages the virtual environment and installs all dependencies declared by the project.
To set up the tool:

```
cd utils/measure
uv venv
uv sync --extra dev
```

#### Start measurements

```
uv run python -m measure.measure
```

The script will ask you a few questions, then proceed taking measurements.

For OCR measurements, install the optional OCR dependencies first:

```
uv sync --extra dev --extra ocr
```

After the measurements are finished you will find the files in `export` directory.

## More information about measuring

See the WIKI article for further documentation https://docs.powercalc.nl/contributing/measure/

## Developing the Home Assistant app locally

The Home Assistant app has a FastAPI backend (`measure/`) and a Lit frontend (`frontend/`). You can run both locally with hot-reloading of the UI.

**Prerequisites:**
- A reachable Home Assistant instance and a long-lived access token (HA → profile → Security → *Long-lived access tokens*). The app proxies real HA entity data, so `/api/entities` needs a live instance.
- Python/uv set up as described under [Native](#native), and Node.js for the frontend.

**Terminal 1 — backend** (from `utils/measure`):
```
uv run python -m measure.app \
  --host 127.0.0.1 --port 8099 \
  --data-root .dev-data \
  --hass-url http://127.0.0.1:8123/api/ \
  --hass-token <LONG_LIVED_TOKEN>
```
The `--hass-url` must end in `/api/`. `--hass-token` may be omitted if `SUPERVISOR_TOKEN` is exported instead. Session state and settings are written to `--data-root` (here `.dev-data`).

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
