# Measure using OCR

Below you'll find instructions how to use the OCR method.

## Installation

- Install tesseract for your OS. <https://tesseract-ocr.github.io/tessdoc/Installation.html>
- Install Python 3.10 and the requirements for the measure utilility see <https://github.com/bramstroker/homeassistant-powercalc/blob/master/utils/measure/README.md#native>

## Running the OCR stream

From the utils/measure directory in a command line:

```shell
python ocr/main.py -t '{tesseract_binary}'
```

Where tesseract_binary is the location of the tesseract executable
On my machine:

```shell
python ocr/main.py -t '/opt/homebrew/Cellar/tesseract/5.1.0/bin/tesseract'
```

## Running the measure tool

Set `POWER_METER` in the .env to `ocr`, and run as usual either native or with docker.
See [measure](measure.md)

## Tested power meters

The OCR tool is tested with Zhurui PR10. Probably others could also work.
