# Subtract group

Use this group to subtract the power of one or more entities from another entity.

You select a base entity using the `entity_id` option and then add one or more entities to subtract from the base entity using the `subtract_entities` option.

## Create group with GUI

You can create a new group with the GUI using this button.

[![config_flow_start](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc)

When this is not working.

- Go to `Settings` -> `Devices & Services`
- Click `Add integration`
- Search and click `Powercalc`

Select `Group` -> `Subtract` and follow the instructions.

## Create group with YAML

```yaml
powercalc:
  sensors:
    - create_group: Subtract
      group_type: subtract
      entity_id: sensor.a
      subtract_entities:
        - sensor.b
        - sensor.c
```
