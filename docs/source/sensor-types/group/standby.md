# Standby Group

The `Standby Group` is a special group designed to monitor the total power consumption of devices when they are in standby mode or turned off. This helps you track the "vampire power" or "phantom load" in your home - the electricity consumed by devices even when they're not actively being used.

## How it works

The standby group automatically collects and sums up:

1. The standby power of all devices that have a `standby_power` configured and are currently in an OFF state
2. The self-usage power of smart switches and other devices that consume power for their own operation

After configuration, you'll end up with two sensors:

- `sensor.all_standby_power` - Shows the total standby power consumption in watts
- `sensor.all_standby_energy` - Tracks the accumulated energy consumption in kWh

## Active group (optional)

Some installations also want a total of what the devices that are currently switched on are using.
Today that value is only available per device.

The active group adds it, and is disabled by default so the meaning of the standby sensors stays
unchanged:

```yaml
powercalc:
  create_active_group: true
```

The same option is available in the global configuration flow, step "Create sensors".

When enabled you get two additional sensors:

- `sensor.all_self_usage_power` - Shows the power of all devices that are currently switched on
- `sensor.all_self_usage_energy` - Tracks the accumulated energy consumption in kWh

A device only takes part while it is switched on. When it is turned off it leaves the group again.
The standby group is not affected by this option.

## Configuration

The standby group is created by default when you set up the Powercalc integration. No additional configuration is needed to start using it.

If you want to disable the standby group, you can do so in the global configuration:

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

## Use cases

The standby group is useful for:

- Identifying how much power your devices consume when not in use
- Finding energy-saving opportunities by identifying devices with high standby power
- Monitoring the baseline power consumption of your home
- Calculating the cost of standby power over time
