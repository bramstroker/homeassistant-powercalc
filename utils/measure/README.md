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

The script will ask you a few questions, than proceed taking measurements.

After the measurements are finished you will find the files in `export` directory.

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
poetry run python -m measure.measure
```

The script will ask you a few questions, than proceed taking measurements.

After the measurements are finished you will find the files in `export` directory.

## More information about measuring

See the WIKI article for further documentation https://docs.powercalc.nl/contributing/measure/

## Building and running docker image locally
docker build -t measure .
docker run --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it measure
