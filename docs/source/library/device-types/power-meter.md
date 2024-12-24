# Power meter

Smart power meter. Powercalc profiles can be used to define the self usage of the IoT device itself.

## JSON

```json
{
  "measure_method": "manual",
  "measure_device": "Some device",
  "name": "Some power meter",
  "standby_power": 0.3,
  "sensor_config": {
    "power_sensor_naming": "{} Device Power",
    "energy_sensor_naming": "{} Device Energy"
  },
  "device_type": "smart_switch",
  "calculation_strategy": "fixed",
  "fixed_config": {
    "power": 0.3
  }
}
```

Following the example above the power for this device will always be 0.3W.
