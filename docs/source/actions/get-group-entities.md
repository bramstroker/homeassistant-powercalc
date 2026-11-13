# Get Group Entities

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.get_group_entities)

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

## Energy calculated from a power group

When an energy group integrates a power group over time, the action returns the source group's power sensor members. The `source_entity` field identifies that power group:

```yaml
sensor.my_group_energy:
  entities:
    - sensor.kitchen_light_power
    - sensor.furnace_power
  source_entity: sensor.my_group_power
```

Groups that sum existing energy meters return their energy sensor members as usual.

For the standby group, the response lists the sensors currently contributing standby power. Individual sensors and energy sensors without a loaded source power group cannot be used with this action.
