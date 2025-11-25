# New Discovery Configuration Structure

Starting from version 1.18.1, the discovery configuration structure has been updated to use a more organized approach.
This document explains how to migrate from the old configuration structure to the new one.

## Deprecated Configuration Keys

The following configuration keys are now deprecated:

- `discovery_exclude_device_types`: Used to exclude specific device types from auto-discovery
- `discovery_exclude_self_usage`: Used to exclude entities with self-usage profiles from auto-discovery
- `enable_autodiscovery`: Used to enable or disable the auto-discovery feature

## New Configuration Structure

In the new configuration structure, all discovery-related settings are grouped under a single `discovery` dictionary key. The new structure provides the same functionality but with a more organized approach.

### Migration Guide

#### Old Configuration (Deprecated)

```yaml
powercalc:
  enable_autodiscovery: true
  discovery_exclude_device_types:
    - light
    - cover
  discovery_exclude_self_usage: true
```

#### New Configuration

```yaml
powercalc:
  discovery:
    enabled: true
    exclude_device_types:
      - light
      - cover
    exclude_self_usage: true
```

## Mapping of Old to New Keys

| Old Key | New Key |
|---------|---------|
| `enable_autodiscovery` | `discovery.enabled` |
| `discovery_exclude_device_types` | `discovery.exclude_device_types` |
| `discovery_exclude_self_usage` | `discovery.exclude_self_usage` |
