# New YAML structure

In Powercalc 1.8.0 the structure of YAML has been changed.
This has been done to stay in line with other HA components and ensure Powercalc keeps working correctly in the future.
The old configuration format will stay working for some time, but I'll remove support in the future. So it's recommended to adopt your configuration. It's a small change.

Old configuration:

```yaml
sensor:
  - platform: powercalc
    entity_id: light.some_light
    fixed:
      power: 50
  - platform: powercalc
    entity_id: light.other_light
    fixed:
      power: 80
```

New configuration. Everything should move under the `powercalc->sensors` key, and `platform` needs to be removed.

```yaml
powercalc:
  sensors:
    - entity_id: light.some_light
      fixed:
        power: 50
    - entity_id: light.other_light
      fixed:
        power: 80
```

!!! note

    You probably already have a `powercalc:` entry in your configuration for global powercalc configuration. You'll need to add `sensors` under that to prevent duplicating the `powercalc:` key.
    When you use <https://www.home-assistant.io/docs/configuration/packages/> you can of course have powercalc sensor definitions scattered accross multiple files.
