![Version](https://img.shields.io/github/v/release/bramstroker/homeassistant-powercalc?style=for-the-badge)
![Downloads](https://img.shields.io/github/downloads/bramstroker/homeassistant-powercalc/total?style=for-the-badge)
![Contributors](https://img.shields.io/github/contributors/bramstroker/homeassistant-powercalc?style=for-the-badge)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
![hacs installs](https://img.shields.io/endpoint.svg?url=https%3A%2F%2Flauwbier.nl%2Fhacs%2Fpowercalc&style=for-the-badge)
[![Coverage Status](https://img.shields.io/coveralls/github/bramstroker/homeassistant-powercalc/badge.svg?branch=master&style=for-the-badge)](https://coveralls.io/github/bramstroker/homeassistant-powercalc?branch=master)

# <img src="https://docs.powercalc.nl/img/logo2_light.svg" width="300">

## ⚡ Turn any device into an energy monitor, no smart plug required

**PowerCalc** estimates energy consumption for devices that can't measure it themselves, like lights, fans and media players, with no extra hardware. Instead of measuring power directly, it **accurately estimates consumption** using smart models based on real measurements, all inside Home Assistant.

On top of power and energy sensors, PowerCalc also creates **cost sensors** to track spending, **utility meters** to break usage down by day, week or month, and **group sensors** to combine devices, rooms or your whole home into a single total.

---

## See it in action

![Preview](https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/docs/source/img/preview.gif)

---

## Why use PowerCalc?

- 💰 **Save money** - no need to buy smart plugs for every device
- 🔍 **Full visibility** - track energy usage across your entire home
- ⚡ **Accurate estimates** - based on real device measurements
- 🔌 **Works out of the box** - huge built-in profile library
- 🧠 **Advanced modeling** - brightness, color, fan speed, and more

---

## How it works

PowerCalc creates **virtual power sensors** in Home Assistant.

For example:
- 💡 Lights → power based on brightness, color, temperature
- 🌀 Fans → power based on speed
- 📺 Other devices → configurable strategies or measured profiles

You get realistic energy data — without physically measuring every device.

---

## Get started

- 👉 **[Quick Start Guide](https://docs.powercalc.nl/quick-start/)**
- 📚 [Full Documentation](https://docs.powercalc.nl)
- 🔎 [Device Profile Library](https://library.powercalc.nl)

---

## 🌍 Community & contributions

PowerCalc is powered by a growing community:

- Contribute new device profiles
- [Share measurements](https://docs.powercalc.nl/contributing/measure/)
- Improve accuracy for everyone

---

## ⭐ Support the project

If PowerCalc helped you:

- ⭐ **Star this repository**
- ☕ [Buy me a coffee](https://www.buymeacoffee.com/bramski)

---

## 🙌 Powered by

[![JetBrains logo.](https://resources.jetbrains.com/storage/products/company/brand/logos/jetbrains.svg)](https://jb.gg/OpenSource)
