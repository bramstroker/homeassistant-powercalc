[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
![hacs installs](https://img.shields.io/endpoint.svg?url=https%3A%2F%2Flauwbier.nl%2Fhacs%2Fpowercalc)
![Version](https://img.shields.io/github/v/release/bramstroker/homeassistant-powercalc)
![Downloads](https://img.shields.io/github/downloads/bramstroker/homeassistant-powercalc/total)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![StandWithUkraine](https://raw.githubusercontent.com/vshymanskyy/StandWithUkraine/main/badges/StandWithUkraine.svg)](https://github.com/vshymanskyy/StandWithUkraine/blob/main/docs/README.md)
[![Coverage Status](https://coveralls.io/repos/github/bramstroker/homeassistant-powercalc/badge.svg?branch=master)](https://coveralls.io/github/bramstroker/homeassistant-powercalc?branch=master)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=bramstroker_homeassistant-powercalc&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=bramstroker_homeassistant-powercalc)

# :zap: PowerCalc: Home Assistant Virtual Power Sensors

PowerCalc is a custom component for Home Assistant to estimate the power consumption (as virtual meters) of lights, fans, smart speakers and other devices, which don't have a built-in power meter. The consumption of light entities is calculated using different strategies to estimate the power usage by looking at brightness, hue/saturation and color temperature. For other entities a generic calculation can be applied, based on the attributes relevant for that entity.

![Preview](https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/assets/preview.gif)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/bramski)

Go to the [Quick Start](https://homeassistant-powercalc.readthedocs.io/en/latest/quick-start.html) for installation instruction.

- [Full Documentation](https://homeassistant-powercalc.readthedocs.io/en/latest/)
- [supported model listing](docs/supported_models.md)
