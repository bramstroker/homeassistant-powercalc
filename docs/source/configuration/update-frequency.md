# Update Frequency and Throttling

This page explains how to control update frequency for different sensors in Powercalc. All options can be set globally in the `powercalc` configuration or via the GUI.

## Sensor Update Behavior

### Individual Sensors
- **Power Sensors**:
  - Update immediately when their source entity changes state
- **Energy Sensors**:
  - Update when power sensor changes state
  - Also update at interval set by `energy_update_interval` even if power remains constant. Setting this to 0 disables time based updates.

### Group Sensors
- **Group Power Sensors**:
  - Throttled by `group_power_update_interval` (default: 2 seconds)
  - Update when member sensors change, respecting throttle interval
- **Group Energy Sensors**:
  - Default update interval: 60 seconds
  - Configurable via `group_energy_update_interval`
  - Set to 0 to disable throttling

### Daily Energy Sensors
- Default update frequency: 30 minutes (1800 seconds)
- Configurable during setup for each sensor

## Configuration Example

```yaml
powercalc:
  energy_update_interval: 120  # Force update every 2 minutes
  group_power_update_interval: 30  # Update group power sensors every 30 seconds
```

## Why Throttling Matters

Throttling helps:
1. **Reduce System Load**: Fewer updates means less computational demand
2. **Prevent Database Bloat**: Fewer state changes recorded
3. **Improve Reliability**: Ensures accurate calculations between updates

## Best Practices
- Default values work well for most setups
- Increase intervals if you have many sensors and notice performance issues
- Decrease intervals for more real-time data, but be mindful of system impact
