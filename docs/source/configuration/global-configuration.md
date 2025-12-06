# Global configuration

Powercalc offers configuration options that can be set globally. These global settings will apply to all sensors created with Powercalc.
However, if you configure settings for an individual sensor, those specific settings will take precedence over the global configuration for that sensor.

Global configuration can be defined both in `configuration.yaml` and in the GUI.
When you define a configuration option in both places, the YAML configuration will take precedence over the GUI configuration.

## GUI configuration

Click the button to go to the Powercalc configuration flow:

[![config_flow_start](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc)

Select `Global configuration` and follow the instructions.

When you'd like the change the configuration later, go to the [Powercalc integration page](https://my.home-assistant.io/redirect/integration/?domain=powercalc), find the `Global configuration` entry and click the cog icon.

![Configure](../img/global_config_configure.png)

!!! note

    Sensors created with the GUI do have a configuration set for `create_energy_sensors`, `create_utility_meters`, `ignore_unavailable_state` and `energy_integration_method`, changing global configuration will not affect the existing GUI configuration entries, to make it easy to change all of them Powercalc provides an action `powercalc.change_gui_config`. Refer to [Change GUI configuration action](#change-gui-configuration-action).

## YAML configuration

You can add the options to `configuration.yaml` under the `powercalc:` property, like so:

```yaml
powercalc:
  power_sensor_naming: "{} Powersensor"
  create_energy_sensors: false
```

!!! tip

    You can hot reload the configuration without restarting Home Assistant by going to `Developer tools`, click `Powercalc` in the `YAML configuration reloading` section.

## Configuration options

All the possible options are listed below.

| Name                          | Type       | Requirement  | Default                | Description                                                                                                                                                                                                                          |
|-------------------------------|------------| ------------ |------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| create_domain_groups          | list       | **Optional** |                        | Create grouped power sensor aggregating all powercalc sensors of given domains, see [domain group](../sensor-types/group/domain.md)                                                                                                  |
| create_energy_sensors         | boolean    | **Optional** | true                   | Let the component automatically create energy sensors (kWh) for every power sensor                                                                                                                                                   |
| create_standby_group          | boolean    | **Optional** | true                   | Create group which sums all standby power consumption and self-usage of IOT devices. See [standby group](../sensor-types/standby.md)                                                                                                  |
| create_utility_meters         | boolean    | **Optional** | false                  | Set to `true` to automatically create utility meters of your energy sensors. See [utility meter](../sensor-types/utility-meter.md)                                                                                                   |
| disable_extended_attributes   | boolean    | **Optional** | false                  | Set to `true` to disable all extra attributes powercalc adds to the power, energy and group entity states. This will help keep the database size small especially when you have a lot of powercalc sensors and frequent update ratio |
| disable_library_download      | boolean    | **Optional** | false                  | Set to `true` to disable the Powercalc library download feature, see [library](../library/library.md)                                                                                                                                |
| discovery                     | dictionary | **Optional** |                        | Control discovery settings. See [discovery options](../library/discovery.md#discovery-configuration)                                                                                                                                 |
| energy_sensor_naming          | string     | **Optional** | {} energy              | Change the name of the sensors. Use the `{}` placeholder for the entity name of your appliance. This will also change the entity_id of your sensor                                                                                   |
| energy_sensor_friendly_naming | string     | **Optional** |                        | Change the friendly name of the sensors, Use `{}` placehorder for the original entity name.                                                                                                                                          |
| energy_sensor_category        | string     | **Optional** |                        | Category for the created energy sensors. See [entity category](entity-category.md).                                                                                                                                                  |
| energy_integration_method     | string     | **Optional** | trapezoid              | Integration method for the energy sensor. See [HA docs](https://www.home-assistant.io/integrations/integration/#method)                                                                                                              |
| energy_sensor_precision       | numeric    | **Optional** | 4                      | Number of decimals you want for the energy sensors. See [HA docs](https://www.home-assistant.io/integrations/integration/#round)                                                                                                     |
| energy_sensor_unit_prefix     | string     | **Optional** |                        | Unit prefix for the energy sensor. See [HA docs](https://www.home-assistant.io/integrations/integration/#unit_prefix). Set to `none` for to create a Wh sensor                                                                       |
| energy_update_interval        | numeric    | **Optional** | 600                    | Enable time based updating of energy sensor once every x seconds. 0 is disabled. See [update-frequency](update-frequency.md)                                                                                                         |
| group_energy_update_interval  | numeric    | **Optional** | 60                     | Throttle state changes of group energy sensor to only once every x seconds. 0 is disabled. See [update-frequency](update-frequency.md)                                                                                               |
| group_power_update_interval   | numeric    | **Optional** | 2                      | Throttle state changes of group power sensor to only once every x seconds. 0 is disabled. See [update-frequency](update-frequency.md)                                                                                                |
| ignore_unavailable_state      | boolean    | **Optional** | false                  | Set to `true` when you want the power sensor to display a value (0 or `standby_power`) regardless of whether the source entity is available.                                                                                         |
| power_sensor_naming           | string     | **Optional** | {} power               | Change the name of the sensors. Use the `{}` placeholder for the entity name of your appliance. This will also change the entity_id of your sensor                                                                                   |
| power_sensor_friendly_naming  | string     | **Optional** |                        | Change the friendly name of the sensors, Use `{}` placehorder for the original entity name.                                                                                                                                          |
| power_sensor_category         | string     | **Optional** |                        | Category for the created power sensors. See [entity category](entity-category.md).                                                                                                                                                   |
| power_sensor_precision        | string     | **Optional** |                        | Number of decimals you want for the power sensors.                                                                                                                                                                                   |
| utility_meter_net_consumption | boolean    | **Optional** | false                  | Enable this if you would like to treat the source as a net meter. This will allow your counter to go both positive and negative. See [utility_net_consumption]                                                                       |
| utility_meter_offset          | string     | **Optional** | 00:00:00               | Offset for the utility meters. Format HH:MM:SS. See [utility_offset]                                                                                                                                                                 |
| utility_meter_types           | list       | **Optional** | daily, weekly, monthly | Define which cycles you want to create utility meters for. See [utility_cycle]                                                                                                                                                       |
| utility_meter_tariffs         | list       | **Optional** |                        | Define different tariffs. See [utility_tariffs].                                                                                                                                                                                     |
| include_non_powercalc_sensors | boolean    | **Optional** | true                   | Control whether you want to include non powercalc sensors in groups. See [include entities](../sensor-types/group/include-entities.md)                                                                                               |

[utility_cycle]: https://www.home-assistant.io/integrations/utility_meter/#cycle
[utility_net_consumption]: https://www.home-assistant.io/integrations/utility_meter/#net_consumption
[utility_offset]: https://www.home-assistant.io/integrations/utility_meter/#offset
[utility_tariffs]: https://www.home-assistant.io/integrations/utility_meter/#tariffs
