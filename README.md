# homeassistant-huepower
Custom component to calculate power consumption of hue lights.
This component uses CSV files to lookup power consumption based on brightness, hue/saturation and color temperature. 

## Installation

Copy `custom_components/huepower` into your Home Assistant `config` directory.

HACS support is coming soon.

## Configuration

Add the following to your configuration.yaml:

```yaml
sensor:
  - platform: huepower
    entity_id: light.livingroom_floorlamp
  - platform: huepower
    entity_id: light.livingroom_ceiling
```

The `entity_id` must be a light entity provided by the `Philips Hue` integration

The model id will be automatically detected by looking at the Hue Bridge API data.
For auto discovery to work you MUST have the  Philips Hue integration enabled.

You can force a certain manufactuer/model when you don't use the Philips HUE api (for example Zigbee stick directly). Or when the manufacturer and model cannot be discovered correctly

```yaml
sensor:
  - platform: huepower
    entity_id: light.livingroom_floorlamp
    manufacturer: signify
    model: LCT010
```

<hr>

## CSV data files

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

### Support for new light

New files are created by taking measurements using a smartplug (i.e. Shelly plug) and changing the light to all kind of different variations using the Hue API.
An example script is available `utils/measure/measure.py`.
I am using the "Shelly Plug S"

## Supported models
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

<hr>

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/bramski)
