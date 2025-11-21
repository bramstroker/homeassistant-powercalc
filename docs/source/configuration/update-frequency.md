# Update Frequency and Throttling

This page explains the various options available for controlling the update frequency of different sensors in Powercalc, as well as the built-in throttling capabilities.
All configuration options mentioned here can be set globally in the `powercalc` configuration section or by using the GUI global configuration.

## Individual Power Sensors

Individual power sensors (created for each device) have the following update frequency characteristics:

- By default, power sensors are throttled to update once per second.
- This means that even if the source entity changes state multiple times within a second, the power sensor will only update once.

## Individual Energy Sensors

Individual energy sensors derive their values from power sensors and have the following update frequency characteristics:

- Energy sensors calculate energy consumption based on power readings. It will update immediately when the power sensor changes state.
- The interval can be set by `energy_update_interval` option. The energy sensor will update based on this interval even if the power sensor stays constant.

## Group Power Sensors

Group power sensors (which combine multiple power sensors) have the following update frequency characteristics:

- Group power sensors are throttled to update once every x seconds, which is configurable by the `group_power_update_interval` option.
- This means that group power sensors will update immediately when any of their member sensors change state, but not more frequently than every 2 seconds.

## Group Energy Sensors

Group energy sensors (which combine multiple energy sensors) have the following update frequency characteristics:

- Group energy sensors have a default update interval of 60 seconds.
- This interval can be configured using the `group_energy_update_interval` option.
- Throttling is applied based on this update interval.
- Setting `group_update_interval` to 0 disables throttling, allowing the sensor to update immediately when any of its member sensors change state.

## Daily Energy Sensors

Daily energy sensors have the following update frequency characteristics:

- Daily energy sensors have a default update frequency of 30 minutes (1800 seconds).
- You can configure this on a per-sensor basis during the configuration flow.

## Configuration Options

You can set global update frequency options in your configuration:

```yaml
powercalc:
  energy_update_interval: 120  # Force update every 2 minutes
  group_power_update_interval: 30   # Update group power sensors every 30 seconds
```

## Throttling Behavior

Throttling in Powercalc serves several purposes:

1. **Reducing System Load**: By limiting how often sensors update, Powercalc reduces the computational load on your Home Assistant instance.
2. **Preventing Database Bloat**: Less frequent updates mean fewer state changes recorded in your database.
3. **Improving Reliability**: Throttling helps ensure that sensors have time to calculate accurate values before updating again.

## Best Practices

- For most setups, the default values work well.
- If you have many sensors and notice performance issues, consider increasing the update intervals.
- If you need more real-time data, you can decrease the update intervals, but be aware of the potential impact on system performance.
