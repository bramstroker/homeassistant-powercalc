# Domain group

Powercalc makes it easy to create a group sensors for all entities of a given domain with the `create_domain_groups` option, or you can use the GUI, select `Group` -> `Domain group`.
For example let's assume you want group sensors for all your lights and media players you can use the following configuration.

```yaml
powercalc:
  create_domain_groups:
    - light
    - media_player
```

!!! note

    This will only include all virtual power sensors created with powercalc, not any other power sensors already available in your HA installation. This is because Powercalc cannot know the source for any given power sensor.

You can also utilize this option to create a group to sum all energy sensors of your HA installation. Use `all` for that.

```yaml
powercalc:
  create_domain_groups:
    - all
```
