##### Dynamically including entities

Powercalc provides several methods to automatically include a bunch of entities in a group with the `include` option.
> Note: only entities will be included which are in the supported models list (these can be auto configured). You can combine `include` and `entities` to extend the group with custom configured entities.

**Include area**

> Available from v0.12 and higher

```yaml
sensor:
  - platform: powercalc
    create_group: Outdoor
    include:
      area: outdoor
```

This can also be mixed with the `entities` option, to add or override entities to the group. i.e.

```yaml
sensor:
  - platform: powercalc
    create_group: Outdoor
    include:
      area: outdoor
    entities:
      - entity_id: light.frontdoor
        fixed:
          power: 100
```

**Include group**

> Available from v0.14 and higher

Includes entities from a Home Assistant [group](https://www.home-assistant.io/integrations/group/) or [light group](https://www.home-assistant.io/integrations/light.group/)

```yaml
sensor:
  - platform: powercalc
    create_group: Livingroom lights
    include:
      group: group.livingroom_lights
```

**Include template**

> Available from v0.14 and higher

```yaml
sensor:
  - platform: powercalc
    create_group: All indoor lights
    include:
      template: {{expand('group.all_indoor_lights')|map(attribute='entity_id')|list}}
```

**Include domain**

> Available from v0.19 and higher

```yaml
sensor:
  - platform: powercalc
    create_group: All lights
    include:
      domain: light
```