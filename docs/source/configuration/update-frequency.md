# Update Frequency & Throttling

This page describes how Powercalc manages update intervals for its
various sensors, and how you can adjust these behaviors.
All settings can be defined globally through YAML under the `powercalc:`
key, or configured via the GUI Global Configuration entry.

## How Sensors Update

### Individual Power Sensors

-   Update immediately whenever the source entity changes state.
-   Additionally update on a fixed interval defined by
    `power_update_interval`, even if power is constant. (default: **disabled**)
-   A new state is **not** written if the calculated power value hasn't
    changed from the previously reported value, unless `power_update_interval` is defined.

### Individual Energy Sensors

-   Update whenever their corresponding power sensor changes.
-   Additionally update on a fixed interval defined by
    `energy_update_interval`, even if power is constant. (default: **10 minutes**)
-   Set to `0` to disable time-based updates.

### Group Power Sensors

-   Updates are throttled using `group_power_update_interval` (default:
    **2 seconds**).
-   All underlying member state changes are processed, but writes to
    Home Assistant respect the throttle interval.
-   Set to `0` to disable throttling entirely.

### Group Energy Sensors

-   Updates are throttled using `group_energy_update_interval` (default:
    **60 seconds**).
-   All underlying member state changes are processed, but writes to
    Home Assistant respect the throttle interval.
-   Set to `0` to disable throttling entirely.

### Daily Energy Sensors

-   Default update interval: **30 minutes (1800 seconds)**.
-   This interval is configurable per sensor during setup.

## Configuration Example

``` yaml
powercalc:
  energy_update_interval: 120              # Update every 2 minutes
  power_update_interval: 600               # Update every 10 minutes
  group_power_update_interval: 30          # Throttle group power updates to 30 seconds
  group_energy_update_interval: 120        # Override default 60 sec group energy updates
```

## Why Throttling Is Important

Throttling helps maintain system performance and data quality:

1.  **Reduces System Load**
    Limits redundant updates, which is useful in setups with many
    sensors.

2.  **Prevents Database Bloat**
    Fewer state changes means fewer writes to the recorder database.

3.  **Improves Reliability**
    Powercalc still processes all underlying state changes internally,
    ensuring accurate calculations even when updates are delayed.

## Best Practices

-   Default intervals are suitable for most installations.
-   Increase update intervals if you have many sensors or notice
    performance issues.
-   Decrease intervals for more real-time readings --- but keep in mind
    the increased system load and recorder usage.
