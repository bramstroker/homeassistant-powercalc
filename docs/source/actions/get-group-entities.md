# Get Group Entities

Use this action to retrieve all the member entity IDs of a group entity.

## Example

```yaml
action: powercalc.get_group_entities
target:
  entity_id: sensor.my_group_power
data: {}
```

Example response:

```yaml
sensor.tracked_power:
  entities:
    - sensor.kitchen_light_power
    - sensor.furnace_power
    - sensor.magic_power
```
