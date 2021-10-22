# Powercalc measure tooling

This package contains everything you need to automatically take measurements of lights to contribute to this repository.

## Setup

**Prerequisites:**
- Make sure you have Python 3 running on your system. version 3.8 or higher is advised.

Setup requirements for the script. It is advised to run in a virtual environment.
```
cd utils/measure
python3 -m venv measure
source measure/bin/activate
pip install -r requirements.txt
```

When this is not working on your machine (i.e. windows) just install globally.
```
cd utils/measure
pip install -r requirements.txt
```

Copy the `.env.dist` file to `.env` and modify the configuration parameters according to your needs.
You will need to select a `POWER_METER` and `LIGHT_CONTROLLER`

## Run

```
python3 measure.py
```

The script will ask you a few questions, than proceed taking measurements.

## Run with docker

`docker run --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it bramgerritsen/powercalc-measure:latest`

To update to the latest version of the script:

`docker pull bramgerritsen/powercalc-measure`

## More information about measuring

See the WIKI article for further documentation https://github.com/bramstroker/homeassistant-powercalc/wiki/Contributing-new-lights
