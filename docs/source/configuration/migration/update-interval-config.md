# New Update interval configuration structure

Starting from version 1.18.1, the `group_update_interval` configuration option has been renamed to `group_power_update_interval`.
Also `force_update_frequency` has been renamed to `energy_update_interval`.

Please update your YAML configuration to reflect this change:

Old:

```yaml
powercalc:
  group_update_interval: 20
  force_update_frequency: 00:00:60
```

New:

```yaml
powercalc:
  group_power_update_interval: 20
  energy_update_interval: 60
```
