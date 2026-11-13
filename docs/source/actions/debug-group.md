# Debug Group

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.debug_group)

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

For energy groups that sum existing energy meters, member values are returned in the unit of the group sensor, for example `kWh`.

## Energy calculated from a power group

Some energy groups integrate a power group over time instead of summing individual energy meters. This includes domain groups such as lights and switches, and custom groups with `force_calculate_group_energy` enabled or without member energy meters.

For these groups, the response contains the energy total and a separate `source_group` with the current power readings:

```yaml
sensor.my_group_energy:
  state: "1.2500"
  unit_of_measurement: kWh
  source_group:
    entity_id: sensor.my_group_power
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

The power readings show current contributions to the source group. They do not represent each member's share of the accumulated energy total.

The action also supports standby, subtract, and tracked/untracked groups and their calculated energy sensors. For standby groups, member values show each sensor's current standby contribution.

Individual sensors and energy sensors without a loaded source power group cannot be used with this action.
