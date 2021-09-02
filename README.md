[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
![Version](https://img.shields.io/github/v/release/bramstroker/homeassistant-powercalc)
![Downloads](https://img.shields.io/github/downloads/bramstroker/homeassistant-powercalc/total)

# Home Assistant Virtual Power Sensors
Custom component to calculate estimated power consumption of lights and other appliances.
Provides easy configuration to get virtual power consumption sensors in Home Assistant for all your devices which don't have a build in power meter.
This component estimates power usage by looking at brightness, hue/saturation and color temperature etc using different strategies. They are explained below.

![Preview](https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/assets/preview.gif)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/bramski)

## TOC
- [Installation](#installation)
    - [HACS](#hacs)
    - [Manual](#manual)
- [Configuration](#configuration)
    - [Sensor](#sensor-configuration)
    - [Global](#global-configuration)
- [Calculation modes](#calculation-modes)
    - [LUT](#lut-mode)
    - [Linear](#linear-mode)
    - [Fixed](#fixed-mode)
- [Light model library](#light-model-library)
    - [LUT data files](#lut-data-files)
      - [Measuring lights](#creating-lut-files)
    - [Supported models](#supported-models)
- [Sensor naming](#sensor-naming)
- [Setting up for energy dashboard](#setting-up-for-energy-dashboard)
    - [Creating energy groups](#creating-energy-groups)
- [Advanced features](#advanced-features)
    - [Multiply Factor](#multiply-factor)
    - [Utility Meters](#utility-meters)
- [Debug logging](#debug-logging)

## Installation

### HACS
This integration is part of the default HACS repository. Just click "Explore and add repository" to install

### Manual
Copy `custom_components/powercalc` into your Home Assistant `config` directory.

### Post installation step
Restart HA

## Configuration

To add virtual sensors for your devices you have to add some configuration to `configuration.yaml`.
Additionally some settings can be applied on global level and will apply to all your virtual power sensors.
After changing the configuration you need to restart HA to get your power sensors to appear.

### Sensor configuration

For each entity you want to create a virtual power sensor for you'll need to add an entry in `configuration.yaml`.
Each virtual power sensor have it's own configuration possibilities.
They are as follows:

| Name                    | Type    | Requirement  | Description                                                                |
| ----------------------- | ------- | ------------ | -------------------------------------------------------------------------- |
| entity_id               | string  | **Required** | HA entity ID. The id of the device you want your power sensor for          |
| manufacturer            | string  | **Optional** | Manufacturer, most of the time this can be automatically discovered        |
| model                   | string  | **Optional** | Model id, most of the time this can be automatically discovered            |
| standby_usage           | float   | **Optional** | Supply the wattage when the device is off                                  |
| disable_standby_usage   | boolean | **Optional** | Set to `true` to not show any power consumption when the device is standby |
| name                    | string  | **Optional** | Override the name                                                          |
| create_energy_sensor    | boolean | **Optional** | Set to disable/enable energy sensor creation. When set this will override global setting `create_energy_sensors` |
| custom_model_directory  | string  | **Optional** | Directory for a custom light model. Relative from the `config` directory   |
| mode                    | string  | **Optional** | Calculation mode, one of `lut`, `linear`, `fixed`                          |
| multiply_factor         | float   | **Optional** | Multiplies the calculated power by this number. See [multiply factor](#multiply-factor) |
| multiply_factor_standby | boolean | **Optional** | When set to `true` the `multiply_factor` will also be applied to the standby usage |
| fixed                   | object  | **Optional** | [Fixed mode options](#fixed-mode)                                          |
| linear                  | object  | **Optional** | [Linear mode options](#linear-mode)                                        |

**Minimalistic example creating two power sensors:**

```yaml
sensor:
  - platform: powercalc
    entity_id: light.hallway
  - platform: powercalc
    entity_id: light.living_room
```

This will add a power sensors with the entity ids `sensor.hallway_power` and `sensor.living_room_power` to your installation.
See [Calculation modes](#calculation-modes) for all possible sensor configurations.

### Global configuration

All these settings are completely optional. You can skip this section if you don't need any advanced configuration.

| Name                   | Type    | Requirement  | Default                | Description                                                                                                                                        |
| ---------------------- | ------- | ------------ | ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| scan_interval          | string  | **Optional** | 00:10:00               | Interval at which the sensor state is updated, even when the power value stays the same. Format HH:MM:SS                                           |
| create_energy_sensors  | boolean | **Optional** | true                   | Let the component automatically create energy sensors (kWh) for every power sensor                                                                 |
| power_sensor_naming    | string  | **Optional** | {} power               | Change the name of the sensors. Use the `{}` placeholder for the entity name of your appliance. This will also change the entity_id of your sensor |
| energy_sensor_naming   | string  | **Optional** | {} energy              | Change the name of the sensors. Use the `{}` placeholder for the entity name of your appliance. This will also change the entity_id of your sensor |
| create_utility_meters  | boolean | **Optional** | false                  | Set to `true` to automatically create utility meters of your energy sensors. See [utility_meters](#utility-meters) |
| utility_meter_types    | list    | **Optional** | daily, weekly, monthly | Define which cycles you want to create utility meters for. See [cycle](https://www.home-assistant.io/integrations/utility_meter/#cycle) |

**Example:**

```yaml
powercalc:
  scan_interval: 00:01:00 #Each minute
  power_sensor_naming: "{} Powersensor"
  create_energy_sensors: false
```

## Calculation modes

To calculate estimated power consumption different modes are supported, they are as follows:
- [LUT (lookup table)](#lut-mode)
- [Linear](#linear-mode)
- [Fixed](#fixed-mode)

### LUT mode
Supported domain: `light`

This is the most accurate mode.
For a lot of light models measurements are taken using smart plugs. All this data is saved into CSV files. When you have the LUT mode activated the current brightness/hue/saturation of the light will be checked and closest matching line will be looked up in the CSV.
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
Supported domains: `light`, `fan` 

The linear mode can be used for dimmable devices which don't have a lookup table available.
You need to supply the min and max power draw yourself, by either looking at the datasheet or measuring yourself with a smart plug / power meter.
Power consumpion is calculated by ratio. So when you have your fan running at 50% speed and define watt range 2 - 6, than the estimated consumption will be 4 watt.

#### Configuration options
| Name              | Type    | Requirement  | Description                                 |
| ----------------- | ------- | ------------ | ------------------------------------------- |
| min_power         | float   | **Optional** | Power usage for lowest brightness level     |
| max_power         | float   | **Optional** | Power usage for highest brightness level    |
| calibrate         | string  | **Optional** | Calibration values                          |

#### Example configuration

```yaml
sensor:
  - platform: powercalc
    entity_id: light.livingroom_floorlamp
    linear:
      min_power: 0.5
      max_power: 8
```

#### Advanced precision calibration

With the `calibrate` setting you can supply more than one power value for multiple brightness/percentage levels.
This allows for a more accurate estimation because not all lights are straight linear.

```yaml
sensor:
  - platform: powercalc
    entity_id: light.livingroom_floorlamp
    linear:
      calibrate:
        - 1 -> 0.3
        - 10 -> 1.25
        - 50 -> 3.50
        - 100 -> 6.8
        - 255 -> 15.3
```

> Note: For lights the supplied values must be in brightness range 1-255, when you select 1 in lovelace UI slider this is actually brightness level 3.
> For fan speeds the range is 1-100 (percentage)

### Fixed mode
Supported domains: `light`, `fan`, `switch`, `binary_sensor`, `device_tracker`, `remote`, `media_player`, `input_boolean`, `input_select`, `sensor`, `climate`, `vacuum`

When you have an appliance which only can be set on and off you can use this mode.
You need to supply a single watt value in the configuration which will be used when the device is ON

#### Configuration options
| Name              | Type    | Requirement  | Description                                           |
| ----------------- | ------- | ------------ | ----------------------------------------------------- |
| power             | float   | **Optional** | Power usage when the appliance is turned on (in watt) |
| states_power      | dict    | **Optional** | Power usage per entity state                          |

#### Simple example
```yaml
sensor:
  - platform: powercalc
    entity_id: light.nondimmabled_bulb
    fixed:
      power: 20
```

#### Power per state
The `states_power` setting allows you to specify a power per entity state. This can be useful for example on Sonos devices which have a different power consumption in different states.

```yaml
sensor:
  - platform: powercalc
    entity_id: media_player.sonos_living
    fixed:
      states_power:
        playing: 8.3
        paused: 2.25
        idle: 1.5
```

You can also use state attributes. Use the `|` delimiter to seperate the attribute and value. Here is en example:

```yaml
sensor:
  - platform: powercalc
    entity_id: media_player.sonos_living
    fixed:
      power: 12
      states_power:
        media_content_id|Spotify: 5
        media_content_id|Youtube: 10
```

When no match is found in `states_power` lookup than the configured `power` will be considered.

## Configuration examples

### Linear mode with additional standby usage

```yaml
sensor:
  - platform: powercalc
    entity_id: light.livingroom_floorlamp
    linear:
      min_power: 0.5
      max_power: 8
    standby_usage: 0.2
    name: My amazing power meter
```

<hr>

## Light model library

The component ships with predefined light measurements for some light models.
This library will keep extending by the effort of community users.

These models are located in `custom_components/powercalc/data` directory.
Each light model has it's own subdirectory `{manufacturer}/{modelid}`

### model.json

Every model MUST contain a `model.json` file which defines the supported calculation modes and other configuration.
See the [json schema](custom_components/powercalc/data/model_schema.json) how the file must be structured or the examples below.

When [LUT mode](#lut-mode) is supported also [CSV lookup files](#lut-data-files) must be provided.

Example lut mode:

```json
{
    "name": "Hue White and Color Ambiance A19 E26 (Gen 5)",
    "standby_usage": 0.4,
    "supported_modes": [
        "lut"
    ],
    "measure_method": "script",
    "measure_device": "Shelly Plug S"
}
```

Example linear mode

```json
{
    "name": "Hue Go",
    "supported_modes": [
        "linear"
    ],
    "standby_usage": 0.2,
    "linear_config": {
        "min_power": 0,
        "max_power": 6
    },
    "measure_method": "manual",
    "measure_device": "From manufacturer specifications"
}
```

### LUT data files

To calculate power consumption a lookup is done into CSV data files.

Depending on the supported color modes of the light the integration expects one or more CSV files here:
 - hs.csv.gz (hue/saturation, colored lamps)
 - color_temp.csv.gz (color temperature)
 - brightness.csv.gz (brightness only lights)

Some lights support two color modes (both hs and color_temp), so there must be two CSV files.

The files are gzipped to keep the repository footprint small, and installation fast.

Example:

```
- signify
  - LCT010
    - hs.csv.gz
    - color_temp.csv.gz
```

#### Expected file structure

- The file **MUST** contain a header row.
- The data rows in the CSV files **MUST** have the following column order:

**hs.csv**
```csv
bri,hue,sat,watt
```

**color_temp.csv**
```csv
bri,mired,watt
```

**brightness.csv**
```csv
bri,watt
```

***Ranges***:
- brightness (0-255)
- hue (0-65535)
- saturation (0-255)
- mired (0-500)  min value depending on min mired value of the light model

#### Creating LUT files

New files are created by taking measurements using a smartplug (i.e. Shelly plug) and changing the light to all kind of different variations using the Hue API or Home Assistant API.
The tooling is available at `utils/measure_v2_`.

The script supports several smartplugs with power monitoring.

See the [README](utils/measure_v2/README.md) for more information.

### Supported models

See the [list](docs/supported_models.md) of supported lights which don't need any manual configuration

## Sensor naming

Let's assume you have a source sensor `light.patio` with name "Patio".
Powercalc will create the following sensors by default.
- sensor.patio_power (Patio power)
- sensor.patio_energy (Patio energy)

> Utility meters will use the energy name as a base and suffix with `_daily`, `_weekly`, `_monthly`

### Change suffixes
To change the default suffixes `_power` and `_energy` you can use the `power_sensor_naming` and `energy_sensor_naming` options.
The following configuration:

```yaml
powercalc:
  energy_sensor_naming: "{} kWh consumed"
```

will create:
- sensor.patio_power (Patio power)
- sensor.patio_kwh_consumed (Patio kWh consumed)

### Change name
You can also change the sensor name with the `name` option

```yaml
sensor:
  - platform: powercalc
    entity_id: light.patio
    name: Patio Light
```

will create:
- sensor.patio_light_power (Patio light power)
- sensor.patio_light_energy (Patio light energy)

## Setting up for energy dashboard
If you want to use the virtual power sensors with the new [energy integration](https://www.home-assistant.io/blog/2021/08/04/home-energy-management/), you have to create an energy sensor which utilizes the power of the powercalc sensor. Starting from v0.4 of powercalc it will automatically create energy sensors for you by default. No need for any custom configuration. These energy sensors then can be selected in the energy dashboard. 

If you'd like to create your energy sensors by your own with e.g. [Riemann integration integration](https://www.home-assistant.io/integrations/integration/), then you can disable the automatic creation of energy sensors with the option `create_energy_sensors` in your configuration (see [global configuration](#global-configuration)).

### Creating energy groups
Let's assume you want to sum up all energy usage from one category e.g. all of your servers. This can easily be achieved by configuring a template sensor. It's essential to add the attributes `last_reset`, `state_class` and `device_class` because these are needed for the sensor to be compatible with the energy integration.  

````yaml
- platform: template
  sensors:
    energy_server:
      friendly_name: "All Server Energy Consumption"
      unit_of_measurement: kWh
      value_template: >-
        {{states('sensor.kingkong_energy') | float + states('sensor.kinglouie_energy') | float}}
      attribute_templates:
        last_reset: "1970-01-01T00:00:00+00:00"
        state_class: measurement
        device_class: energy
        icon: mdi:counter
````
> **Don't** create a template sensor which sums up all values from the power sensors and use this sensor to create a energy sensor because this won't work as you would expect. It 
> wouldn't update in regular bases and as a consequence wont be shown in the energy dashboard in the right timeslots.

## Advanced features

### Multiply Factor

This feature allows you to multiply the calculated power.

This can be useful in the following use cases:
- You have a bunch of similar lights which you control as a group and want a single power sensor.
- You are using a LED strip from the LUT models, but you have extended or shortened it.

Let's assume you have a combination of 4 GU10 spots in your ceiling in a light group `light.livingroom_spots`

```yaml
- platform: powercalc
  entity_id: light.livingroom_spots
  multiply_factor: 4
```

This will add the power sensor `sensor.livingroom_spots_power` and the measured power will be multiplied by 4, as the original measurements are for 1 spot.

By default the multiply factor will **NOT** be applied to the standby usage, you can set the `multiply_factor_standby` to do this.

```yaml
- platform: powercalc
  entity_id: light.livingroom_spots
  multiply_factor: 4
  multiply_factor_standby: true
```

> Note: a multiply_factor lower than 1 will decrease the power. For example 0.5 will half the power.

## Utility meters

The energy sensors created by the component will keep increasing the total kWh, and never reset.
When you want to know the energy consumed the last 24 hours, or last month you can use the [utility_meter](https://www.home-assistant.io/integrations/utility_meter/) component of Home Assistant. Powercalc allows you to automatically create utility meters for all your powercalc sensors with a single line of configuration.

```yaml
powercalc:
  create_utility_meters: true
```

By default utility meters are created for `daily`, `weekly`, `monthly` cycles.
You can change this behaviour with the `utility_meter_types` configuration option.

```yaml
powercalc:
  create_utility_meters: true
  utility_meter_types:
    - daily
    - yearly
```

The utility meters have the same name as your energy sensor, but are extended by the meter cycle.
Assume you have a light `light.floorlamp_livingroom`, than you should have the following sensors created:
- `sensor.floorlamp_livingroom_power`
- `sensor.floorlamp_livingroom_energy`
- `sensor.floorlamp_livingroom_energy_daily`
- `sensor.floorlamp_livingroom_energy_weekly`
- `sensor.floorlamp_livingroom_energy_monthly`

## Debug logging

Add the following to configuration.yaml:

```yaml
logger:
  default: warning
  logs:
    custom_components.powercalc: debug
```
