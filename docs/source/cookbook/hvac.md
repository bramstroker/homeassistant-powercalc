# HVAC Devices

This recipe demonstrates how to set up virtual power sensors for HVAC (Heating, Ventilation, and Air Conditioning) devices. HVAC systems typically have different power consumption levels based on their operating mode (heating, cooling, fan-only) and fan speed.

## Basic Configuration

For a simple HVAC setup where you know the approximate power consumption for different modes, you can use the [fixed strategy](../strategies/fixed.md) with [states_power](../strategies/fixed.md#power-per-state) option.

```yaml
powercalc:
  sensors:
    - entity_id: climate.living_room
      name: Living Room HVAC Power
      fixed:
        states_power:
          hvac_action|cooling: 200
          hvac_action|heating: 350
```

# Todo : Add fan speed handling example
