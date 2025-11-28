# Dynamically including entities

Powercalc provides several methods to automatically include a bunch of entities in a group with the `include` option. The `include` option is used to set the initial entity set for your group.
In addition to that you can use `filter` options to further narrow down this initial set by excluding certain entities.

!!! note

    Only entities will be included which are in the [supported models](https://library.powercalc.nl) list (these can be auto configured). You can combine `include` and `entities` to extend the group with custom configured entities.

!!! important

    Powercalc will include any power sensors found in your HA installation matching the include rules. When you don't want that see [Exclude non powercalc sensors]

Currently Powercalc will not dynamically reload the group when entities are added or removed from your HA installation.
When you created the group using the GUI you can use the `Reload` button on the integration page for the corresponding config entry.
If you used YAML you need to restart Home Assistant fully to reload the group.

## Include

### Area

```yaml
powercalc:
  sensors:
    - create_group: Outdoor
      include:
        area: outdoor
```

This can also be mixed with the `entities` option, to add or override entities to the group. i.e.

```yaml
powercalc:
  sensors:
    - create_group: Outdoor
      include:
        area: outdoor
      entities:
        - entity_id: light.frontdoor
          fixed:
            power: 100
```

### Floor

```yaml
powercalc:
  sensors:
    - create_group: First Floor
      include:
        floor: first_floor
```

This will include all entities that are in areas assigned to the specified floor. Like area filtering, this can be combined with other options:

### Group

Includes entities from an existing Home Assistant [group](https://www.home-assistant.io/integrations/group/) or [light group](https://www.home-assistant.io/integrations/light.group/))

```yaml
powercalc:
  sensors:
    - create_group: Livingroom lights
      include:
        group: group.livingroom_lights
```

### Domain

```yaml
powercalc:
  sensors:
    - create_group: All lights
      include:
        domain: light
```

You might also filter by multiple domains:

```yaml
powercalc:
    sensors:
      - create_group: All lights
        include:
          domain:
            - light
            - switch
```

### Label

Filters entities by a [label](https://www.home-assistant.io/docs/organizing/labels/).

```yaml
powercalc:
  sensors:
    - create_group: All bluetooth proxy
      include:
        label: bluetooth_proxy
```

### Wildcard

Match certain entity id's by a wildcard pattern

`*` matches any character
`?` matches a single character

When you don't supply any of the above wildcard the filter checks for an exact match of the entity_id

```yaml
powercalc:
  sensors:
    - create_group: Office spots
      include:
        wildcard: light.office_spot_*
```

### Template

```yaml
powercalc:
  sensors:
    - create_group: All indoor lights
      include:
        template: {{expand('group.all_indoor_lights')|map(attribute='entity_id')|list}}
```

!!! warning

    The template option sometimes does not work correctly because of loading order of components in HA which powercalc cannot influence.
    So it's actually discouraged to use this and should only be used when you have no other options.

### All

Include all powercalc sensors and other power sensors of the HA installation in the group.
You can combine that with the filters mentioned below.

```yaml
powercalc:
  sensors:
    - create_group: General
      include:
        all:
```

## Filters

While the `include` options above are used to set the initial entity set for your group, you can also apply additional `filter` options to further narrow down this initial set.
These filters accept the same configuration as the include options described above, but they are applied after the initial entity set is determined by the `include` options.

For example to include all light entities from area outdoor.

```yaml
powercalc:
  sensors:
    - create_group: Outdoor lights
      include:
        area: outdoor
        filter:
          domain: light
```

To exclude sensors based on a label:

```yaml
powercalc:
  sensors:
    - create_group: All lights
      include:
        domain: light
        filter:
          label: excludePowercalc
```

### AND/OR

You can also chain nested filter using and / or construction:

```yaml
powercalc:
  sensors:
    - create_group: Outdoor lights
      include:
        area: outdoor
        filter:
          or:
            - domain: light
            - wildcard: switch.pond
            - and:
              - domain: binary_sensor
              - wildcard: "*swimming_pool*"
```

## Exclude non powercalc sensors

By default all the include options will include any power and/or energy sensor from your system, also power sensors provided by other integrations.
When you don't want that behaviour you can set `include_non_powercalc_sensors` to `false`.

```yaml
.. code-block:: yaml

powercalc:
  sensors:
    - create_group: Outdoor lights
      include:
        area: outdoor
        include_non_powercalc_sensors: false
```

You can also set this option globally:

```yaml
.. code-block:: yaml

powercalc:
  include_non_powercalc_sensors: false
```
