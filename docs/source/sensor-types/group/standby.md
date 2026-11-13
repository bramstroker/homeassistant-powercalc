# Standby Group

The `Standby Group` is a special group designed to monitor the total power consumption of devices when they are in standby mode or turned off. This helps you track the "vampire power" or "phantom load" in your home - the electricity consumed by devices even when they're not actively being used.

## How it works

The standby group automatically collects and sums up:

1. The standby power of all devices that have a `standby_power` configured and are currently in an OFF state
2. The self-usage power of smart switches and other devices that consume power for their own operation

After configuration, you'll end up with two sensors:

- `sensor.all_standby_power` - Shows the total standby power consumption in watts
- `sensor.all_standby_energy` - Tracks the accumulated energy consumption in kWh

!!! note

    The self usage of a device that is switched on is part of this total by design. A smart plug that
    draws 0.7 W for its own operation contributes that value whether the connected load is on or off.
    The active consumption of the load itself is not part of the standby total.

## Active group (optional)

Devices that are switched on are excluded from the standby total, unless their profile declares a
self usage for the ON state. If you also want a total of what the devices that are currently
switched on are using, enable the active group in the global configuration.

### Using YAML configuration

```yaml
powercalc:
  create_active_group: true
```

### Using the GUI

1. Go to `Settings` -> `Devices & Services`
2. Find and click on `Powercalc`
3. Click on `Configure` for the Global Configuration entry
4. Go to the "Create sensors" step
5. Enable "Create active group"
6. Click `Submit`

This creates two additional sensors:

- `sensor.all_self_usage_power` - Sum of the power of all devices that are currently switched on
- `sensor.all_self_usage_energy` - Tracks the accumulated energy consumption in kWh

A device only takes part while it is switched on. When it is turned off, its power moves to the
standby total - and back again when it is switched on. The active group is disabled by default and
does not change the meaning of the existing standby sensors.

## Configuration

The standby group is created by default when you set up the Powercalc integration. No additional configuration is needed to start using it.

If you want to disable the standby group, you can do so in the global configuration. This also disables the active group:

### Using YAML configuration

```yaml
powercalc:
  create_standby_group: false
```

### Using the GUI

1. Go to `Settings` -> `Devices & Services`
2. Find and click on `Powercalc`
3. Click on `Configure` for the Global Configuration entry
4. Uncheck the "Create standby group" option
5. Click `Submit`

## Adding devices to the standby group

Devices are automatically included in the standby group when:

1. They have a `standby_power` value configured in their Powercalc configuration
2. They are smart switches or other devices with self-usage profiles

### Example configuration with standby power

```yaml
powercalc:
  entities:
    - entity_id: switch.my_device
      standby_power: 0.5  # 0.5W of standby power when the device is OFF
      # other configuration...
```

### Example configuration with a self usage for the ON state

A library profile can declare the power a device draws for its own operation while it is switched
on with `standby_power_on`. The same value can be set on a manually configured sensor:

```yaml
powercalc:
  sensors:
    - entity_id: sensor.my_router
      mode: fixed
      fixed:
        power: 12.4
      standby_power: 12.4
      standby_power_on: 12.4  # own draw while the device is running
```

## Use cases

The standby group is useful for:

- Identifying how much power your devices consume when not in use
- Finding energy-saving opportunities by identifying devices with high standby power
- Monitoring the baseline power consumption of your home
- Calculating the cost of standby power over time
