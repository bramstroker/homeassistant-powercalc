# Debug Group

Use this action to retrieve a debug overview of a Powercalc group sensor.

The response contains:

- The current state of the group sensor
- The unit of the group sensor
- All member entities with their current values converted to the group unit

This is useful when you want to verify which entities are part of a group and how much each member currently contributes to the total.

## Example

```yaml
action: powercalc.debug_group
target:
  entity_id: sensor.my_group_power
data: {}
```

Example response:

```yaml
sensor.my_group_power:
  state: "150.00"
  unit_of_measurement: W
  members:
    sensor.kitchen_light_power:
      state: "50.00"
      unit_of_measurement: W
    sensor.furnace_power:
      state: "100.00"
      unit_of_measurement: W
```

For energy groups the values are returned in the unit of the group sensor, for example `kWh`.
