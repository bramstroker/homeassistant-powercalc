# homeassistant-huepower
Custom component to calculate power consumption of lights and other appliances.
Provides easy configuration to get power consumption sensors in Home Assistant for all your devices which don't have a build in power meter.
This component estimates power usage by looking at brightness, hue/saturation and color temperature etc using different strategies. They are explained below.

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/bramski)

## Installation

Copy `custom_components/huepower` into your Home Assistant `config` directory.

HACS support is coming soon.

## Calculation modes

To calculate estimated power consumption different modes are support, they are as follows:
- LUT (lookup table)
- Linear
- Fixed

### LUT mode
This is the most accurate mode.
For some models from the Philips Hue line measurements are taken using smart plugs. All this data is saved into CSV files. When you have the LUT mode activated the current brightness/hue/saturation of the light will be checked and closest matching line will be looked up in the CSV.
#todo link supported

#### Configuration

```yaml
sensor:
  - platform: huepower
    entity_id: light.livingroom_floorlamp
    manufacturer: signify
    model: LCT010
```

When you are using the official Philips Hue integration the manufacturer and model can automatically be discovered, so there is no need to supply those.

```yaml
sensor:
  - platform: huepower
    entity_id: light.livingroom_floorlamp
```

### Linear mode
The linear mode can be used for dimmable devices which don't have a lookup table available.
You need to supply the min and max power draw yourself, by eighter looking at the datasheet or measuring yourself with a smart plug / power meter.

#### Configuration

```yaml
sensor:
  - platform: huepower
    entity_id: light.livingroom_floorlamp
    min: 0.5
    max: 8
```

### Fixed mode
When you have an appliance which only can be set on and off you can use this mode.
You need to supply a single watt value in the configuration which will be used when the device is ON

```yaml
sensor:
  - platform: huepower
    entity_id: light.nondimmabled_bulb
    watt: 20
```

## Additional configuration options

`standby_usage`: Supply the wattage when the device is off
`name`: Override the name

<hr>

## LUT data files

To calculate power consumtion a lookup is done into CSV data files.

These files are located in `custom_components/huepower/data` directory.
Each light model has it's own subdirectory `{manufactuer}/{modelid}`
Depending on the supported color modes the integration expects multiple CSV files here:
 - hs.csv (hue/saturation, colored lamps)
 - color_temp.csv (color temperature)

Some lights support both color modes, so there must be two CSV files.

Example:

```
- signify
  - LCT010
    - hs.csv
    - color_temp.csv
```

### Expected file structure

hs.csv:

```
brightness,hue,saturation,watt
```

color_temp.csv

```
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
- Signify LCT003 (hs and color_temp)
- Signify LCT010 (hs and color_temp)
- Signify LCT012 (hs and color_temp). Thanks Simon Hörrle
- Signify LTW001 (color_temp)

## Debug logging

Add the following to configuration.yaml:

```yaml
logger:
  default: warning
  logs:
    custom_components.huepower: debug
```
