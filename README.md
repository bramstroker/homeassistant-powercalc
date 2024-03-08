![Version](https://img.shields.io/github/v/release/bramstroker/homeassistant-powercalc?style=for-the-badge)
![Downloads](https://img.shields.io/github/downloads/bramstroker/homeassistant-powercalc/total?style=for-the-badge)
![Contributors](https://img.shields.io/github/contributors/bramstroker/homeassistant-powercalc?style=for-the-badge)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
![hacs installs](https://img.shields.io/endpoint.svg?url=https%3A%2F%2Flauwbier.nl%2Fhacs%2Fpowercalc&style=for-the-badge)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge)](https://github.com/psf/black)
[![Code style: black](https://img.shields.io/badge/type%20checked-mypy-blue.svg?style=for-the-badge)](https://mypy-lang.org/)
[![Coverage Status](https://img.shields.io/coveralls/github/bramstroker/homeassistant-powercalc/badge.svg?branch=master&style=for-the-badge)](https://coveralls.io/github/bramstroker/homeassistant-powercalc?branch=master)
[![Sonar quality gate](https://img.shields.io/sonar/alert_status/bramstroker_homeassistant-powercalc/master?server=https%3A%2F%2Fsonarcloud.io&style=for-the-badge)](https://sonarcloud.io/summary/new_code?id=bramstroker_homeassistant-powercalc)
[![BuyMeACoffee](https://img.shields.io/badge/-buy_me_a%C2%A0coffee-gray?logo=buy-me-a-coffee&style=for-the-badge)](https://www.buymeacoffee.com/bramski)

# :zap: PowerCalc: Home Assistant Virtual Power Sensors

PowerCalc is a custom component for Home Assistant to estimate the power consumption (as virtual meters) of lights, fans, smart speakers and other devices, which don't have a built-in power meter. The consumption of light entities is calculated using different strategies to estimate the power usage by looking at brightness, hue/saturation and color temperature. For other entities a generic calculation can be applied, based on the attributes relevant for that entity.

Also a measure utility is included which allows user to measure there lights and other devices and contribute power profiles to the Powercalc library.

![Preview](https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/assets/preview.gif)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/bramski)

Go to the [Quick Start](https://homeassistant-powercalc.readthedocs.io/en/latest/quick-start.html) for installation instruction.

- [Full Documentation](https://homeassistant-powercalc.readthedocs.io/en/latest/)
- [Supported model listing](docs/supported_models.md)
