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

## Building and running docker image locally
```
docker build -t measure .
docker run --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it measure
```
