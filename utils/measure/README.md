# Powercalc measure tooling

This package contains everything you need to automatically take measurements of lights to contribute to this repository.

## Setup

There are two ways to run the measure script, using Docker and natively using Python
The recommended way is with docker as all the needed dependencies are bundled.

### Docker

**Prerequisites:**
- Install docker engine, see https://docs.docker.com/get-docker/
- Start up the command line and verify docker is running: `docker version`
- Create a new directory. for example `powercalc-measure`
- Go to this directory and copy the `.env.dist` file to `.env`. You can find it [here](https://github.com/bramstroker/homeassistant-powercalc/blob/master/utils/measure/.env.dist)
- Modify the `.env` file to your needs 

#### Start measurements

Go to the directory you created in a command line and run:

`docker run --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it bramgerritsen/powercalc-measure:latest`

The script will ask you a few questions, than proceed taking measurements.

After the measurements are finished you will find the files in `export` directory.

To update to the latest version of the script:

`docker pull bramgerritsen/powercalc-measure`

### Native

Use this installation method when the docker method is not working for you or you want to do any development on the script.

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

#### Start measurements

```
python3 measure.py
```

The script will ask you a few questions, than proceed taking measurements.

After the measurements are finished you will find the files in `export` directory.

## More information about measuring

See the WIKI article for further documentation https://github.com/bramstroker/homeassistant-powercalc/wiki/Contributing-new-lights
