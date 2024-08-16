# Utility meters

The energy sensors created by the component will keep increasing the total kWh, and never reset.
When you want to know the energy consumed the last 24 hours, or last month you can use the [utility_meter](https://www.home-assistant.io/integrations/utility_meter/) component of Home Assistant. Powercalc allows you to automatically create utility meters for all your powercalc sensors with a single line of configuration.

Toggling utility meter creation on/off can also be done when creating power sensors with the GUI on a per sensor basis.

To create utility meters for all powercalc sensors globally add the following configuration to `configuration.yaml`.

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

!!! note

    A note on [naming](../misc/naming.md).
    The utility meters have the same name as your energy sensor, but are extended by the meter cycle.
    Assume you have a light `light.floorlamp_livingroom`, than you should have the following sensors created:

    - `sensor.floorlamp_livingroom_power`
    - `sensor.floorlamp_livingroom_energy`
    - `sensor.floorlamp_livingroom_energy_daily`
    - `sensor.floorlamp_livingroom_energy_weekly`
    - `sensor.floorlamp_livingroom_energy_monthly`

## Tariffs

When your utility company uses different tariffs depending on the time of the day, i.e. `peak`, `offpeak` you can create multiple utility meters for that use case.
Two `utility_meter` entities will be created and one `select` entity which allows you to select the active tariff.
You can create an automation to set the active tariff depending on time of the day or some other logic, see <https://www.home-assistant.io/integrations/utility_meter/#advanced-configuration>

Use the `utility_meter_tariffs` option to set the tariffs. In the example below we do it globally, but you can also configure per sensor.

```yaml
powercalc:
  utility_meter_tariffs:
    - peak
    - offpeak
```

If you also would like to create an overall utility meter you can add `general` to the list of tariffs.
This will also create a "normal" utility meter, which is also created when you omit the `utility_meter_tariffs` option.

```yaml
powercalc:
  utility_meter_tariffs:
    - general
    - peak
    - offpeak
```
