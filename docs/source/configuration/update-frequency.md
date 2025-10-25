# Update Frequency and Throttling

This page explains the various options available for controlling the update frequency of different sensors in Powercalc, as well as the built-in throttling capabilities.

## Individual Power Sensors

Individual power sensors (created for each device) have the following update frequency characteristics:

- By default, power sensors are throttled to update once per second.
- This means that even if the source entity changes state multiple times within a second, the power sensor will only update once.

## Individual Energy Sensors

Individual energy sensors derive their values from power sensors and have the following update frequency characteristics:

- Energy sensors calculate energy consumption based on power readings.
- They can be configured to force updates at a specific frequency using the `force_update_frequency` option.
- The default force update frequency is 10 minutes.

## Group Power Sensors

Group power sensors (which combine multiple power sensors) have the following update frequency characteristics:

- Group power sensors are throttled to update once every 2 seconds.
- This means that group power sensors will update immediately when any of their member sensors change state, but not more frequently than every 2 seconds.

## Group Energy Sensors

Group energy sensors (which combine multiple energy sensors) have the following update frequency characteristics:

- Group energy sensors have a default update interval of 60 seconds.
- This interval can be configured using the `group_update_interval` option.
- Throttling is applied based on this update interval.
- Setting `group_update_interval` to 0 disables throttling, allowing the sensor to update immediately when any of its member sensors change state.

## Daily Energy Sensors

Daily energy sensors have the following update frequency characteristics:

- Daily energy sensors have a default update frequency of 30 minutes (1800 seconds).
- This is a fixed value and cannot be configured.

## Configuration Options

You can set global update frequency options in your configuration:

```yaml
powercalc:
  force_update_frequency: 00:05:00  # Force update every 5 minutes
  group_update_interval: 120   # Update group energy sensors every 2 minutes (in seconds)
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
