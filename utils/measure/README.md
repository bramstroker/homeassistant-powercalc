# Powercalc measure tooling

This package contains everything you need to automatically take measurements of lights to contribute to this repository.

## Setup

There are two ways to run the measure script, using Docker and natively using Python.
The recommended way is with docker as all the needed dependencies are bundled.

### Docker

**Prerequisites:**
- Install docker engine, see https://docs.docker.com/get-docker/
- Start up the command line and verify docker is running: `docker version`
- Create a new directory. for example `powercalc-measure`
- Go to this directory and copy the `.env.dist` file to `.env`. You can find it [here](https://github.com/bramstroker/homeassistant-powercalc/blob/master/utils/measure/.env.dist)
- Modify the `.env` file to your needs. Selecting the `POWER_METER` and `LIGHT_CONTROLLER` here is mandatory

#### Start measurements

Go to the directory you created in a command line and run:

`docker run --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it bramgerritsen/powercalc-measure:latest`

If running Docker on Windows, replace `$(pwd)` with `%CD%`.

The script will ask you a few questions, than proceed taking measurements.

After the measurements are finished you will find the files in `export` directory.

To update to the latest version of the script:

`docker pull bramgerritsen/powercalc-measure`

### Native

Use this installation method when the docker method is not working for you or you want to do any development on the script.

**Prerequisites:**
- Make sure you have Python 3 running on your system. Version 3.12 is recommended.
- Install poetry. `curl -sSL https://install.python-poetry.org | python3 -` or see https://python-poetry.org/docs/

Poetry allows you to create virtual environment and manage dependencies.
To install the dependencies:

```
cd utils/measure
poetry install
```

#### Start measurements

```
poetry run python measure.py
```

The script will ask you a few questions, than proceed taking measurements.

After the measurements are finished you will find the files in `export` directory.

## More information about measuring

See the WIKI article for further documentation https://docs.powercalc.nl/contributing/measure

## Building and running docker image locally
docker build -t measure .
docker run --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it measure
