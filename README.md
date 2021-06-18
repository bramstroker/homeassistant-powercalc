[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
![Version](https://img.shields.io/github/v/release/bramstroker/homeassistant-powercalc)

# homeassistant-powercalc
Custom component to calculate power consumption of lights and other appliances.
Provides easy configuration to get power consumption sensors in Home Assistant for all your devices which don't have a build in power meter.
This component estimates power usage by looking at brightness, hue/saturation and color temperature etc using different strategies. They are explained below.
Power sensors can be created for `light`, `switch`, `fan` and `binary_sensor` entities 

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/bramski)

## Installation

### HACS
This integration is part of the default HACS repository. Just click "Explore and add repository" to install

### Manual
Copy `custom_components/powercalc` into your Home Assistant `config` directory.


## Calculation modes

To calculate estimated power consumption different modes are support, they are as follows:
- LUT (lookup table)
- Linear
- Fixed

### LUT mode
Supported platforms: `light`

This is the most accurate mode.
For some models from the Philips Hue line measurements are taken using smart plugs. All this data is saved into CSV files. When you have the LUT mode activated the current brightness/hue/saturation of the light will be checked and closest matching line will be looked up in the CSV.
- [Supported models](#supported-models) for LUT mode
- [LUT file structure](#lut-data-files)


#### Configuration

```yaml
sensor:
  - platform: powercalc
    entity_id: light.livingroom_floorlamp
    manufacturer: signify
    model: LCT010
```

When you are using the official Philips Hue integration the manufacturer and model can automatically be discovered, so there is no need to supply those.

```yaml
sensor:
  - platform: powercalc
    entity_id: light.livingroom_floorlamp
```

### Linear mode
Supported platforms: `light`, `fan`

The linear mode can be used for dimmable devices which don't have a lookup table available.
You need to supply the min and max power draw yourself, by eighter looking at the datasheet or measuring yourself with a smart plug / power meter.
Power consumpion is calculated by ratio. So when you have your fan running at 50% speed and define watt range 2 - 6, than the estimated consumption will be 4 watt.

#### Configuration

```yaml
sensor:
  - platform: powercalc
    entity_id: light.livingroom_floorlamp
    mode: linear
    min_watt: 0.5
    max_watt: 8
```

### Fixed mode
Supported platforms: `light`, `fan`, `switch`, `binary_sensor`

When you have an appliance which only can be set on and off you can use this mode.
You need to supply a single watt value in the configuration which will be used when the device is ON

```yaml
sensor:
  - platform: powercalc
    entity_id: light.nondimmabled_bulb
    mode: fixed
    watt: 20
```

## Additional configuration options

- `standby_usage`: Supply the wattage when the device is off
- `name`: Override the name

Full example:

```yaml
sensor:
  - platform: powercalc
    entity_id: light.livingroom_floorlamp
    mode: linear
    min_watt: 0.5
    max_watt: 8
    standby_usage: 0.2
    name: My amazing power meter
```

<hr>

## LUT data files

To calculate power consumtion a lookup is done into CSV data files.

These files are located in `custom_components/powercalc/data` directory.
Each light model has it's own subdirectory `{manufactuer}/{modelid}`
Depending on the supported color modes the integration expects multiple CSV files here:
 - hs.csv.gz (hue/saturation, colored lamps)
 - color_temp.csv.gz (color temperature)

Some lights support both color modes, so there must be two CSV files.

The files are gzipped to keep the repository footprint small, and installation fast.

Example:

```
- signify
  - LCT010
    - hs.csv.gz
    - color_temp.csv.gz
```

### Expected file structure

The data rows in the CSV files MUST have the following column order:

**hs.csv**
```csv
brightness,hue,saturation,watt
```

**color_temp.csv**
```csv
brightness,mired,watt
```

***Ranges***:
- brightness (0-255)
- hue (0-65535)
- saturation (0-255)
- mired (0-500)  min value depending on min mired value of the light model

### Creating LUT files

New files are created by taking measurements using a smartplug (i.e. Shelly plug) and changing the light to all kind of different variations using the Hue API.
An example script is available `utils/measure/measure.py`.
I am using the "Shelly Plug S"

### Supported models
- Signify LCA001 (hs and color_temp)
- Signify LCT003 (hs and color_temp)
- Signify LCT010 (hs and color_temp)
- Signify LCT012 (hs and color_temp)
- Signify LCT015 (color_temp)
- Signify LTW001 (color_temp)

## Debug logging

Add the following to configuration.yaml:

```yaml
logger:
  default: warning
  logs:
    custom_components.powercalc: debug
```
