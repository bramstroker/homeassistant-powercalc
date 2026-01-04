# Analytics

Powercalc can optionally send a small amount of anonymous, aggregated usage data. This helps us understand real-world usage and improve the integration over time.

This feature is **opt-in**, can be disabled at any time.

!!! note

    This feature was introduced in v1.20.0-beta.1. Versions before this do not send analytics.

---

## Why we collect analytics

We collect analytics to:

- understand how Powercalc is used in real installations
- prioritize development and maintenance work
- improve accuracy and library coverage (e.g. which manufacturers/models are most used)
- spot breaking changes more quickly (e.g. version adoption)

---

## What data is collected

The payload only contains **aggregated counts**, for example:

- total number of Powercalc entities
- counts per sensor type (e.g. virtual power, group, daily energy)
- counts per manufacturer and model (aggregated)
- counts per device type (e.g. light, smart_switch)
- counts per calculation strategy (e.g. lut, fixed)
- counts per source domain (e.g. light, switch, input_boolean)
- counts per group type (e.g. custom, standby)
- counts per entity type (e.g. power_sensor, energy_sensor, utility_meter)
- group sizes (number of entities in each group)
- whether group includes are used
- Powercalc version and Home Assistant version
- installation date
- your country-code (derived server-side from your IP-address), example: "NL" for Netherlands.

No per-device identifiers are included.

??? abstract "example JSON payload"

    ```json
    {
      "counts": {
        "by_model": {
          "signify:LCT024": 2,
          "signify:LLC020": 2,
          "shelly:shelly plug s": 1
        },
        "by_config_type": {
          "gui": 8
        },
        "by_sensor_type": {
          "group": 1,
          "real_power": 1,
          "virtual_power": 6
        },
        "by_manufacturer": {
          "shelly": 1,
          "signify": 4
        },
        "by_device_type": {
          "light": 4,
          "plug": 1
        },
        "by_strategy": {
          "lut": 4,
          "fixed": 1
        },
        "by_source_domain": {
          "light": 4,
          "switch": 1
        },
        "by_group_type": {
          "custom": 1,
          "standby": 1
        },
        "by_entity_type": {
          "power_sensor": 5,
          "energy_sensor": 3
        }
      },
      "ha_version": "2025.10.0.dev0",
      "install_id": "081ac191-2667-4242-8226-ecc66b1f7e9e",
      "install_date": "2023-01-15T12:34:56.789012",
      "language": "en",
      "group_sizes": {
        "2": 1,
        "5": 1
      },
      "powercalc_version": "0.1.1",
      "config_entry_count": 8,
      "custom_profile_count": 12,
      "has_global_gui_config": true,
      "has_group_include": false
    }
    ```

---

## What data is *not* collected

We do **not** collect:

- entity IDs, device names, areas, or configuration contents
- your Home Assistant URL, username, or any credentials
- energy usage, power readings, or historical sensor data
- IP addresses or precise location data

---

## Opt-in and disabling

Analytics is **disabled by default**.

### How to enable analytics

You can enable analytics in two ways:

#### Using the GUI

See [Global Configuration](../configuration/global-configuration.md) how to modify the global configuration options
You can find the toggle in `Basic Options`

#### Using YAML configuration

Add the following to your `configuration.yaml` file:

```yaml
powercalc:
  enable_analytics: true
```

### Disabling analytics

If you've enabled analytics, you can disable it at any time by:

- Turning off the option in the GUI configuration
- Setting `enable_analytics: false` in your YAML configuration

---

## Data retention and access

We keep analytics data only as long as needed to support development and maintenance of Powercalc.

Access to the data is restricted to the Powercalc maintainer(s).

---

## Questions or concerns?

If you have questions about what is collected or why, please open a discussion or issue on the Powercalc GitHub repository.

## Insights

There are some nice dashboards available that use the collected analytics data to provide insights into Powercalc usage.
They can be found on the Powercalc website: https://library.powercalc.nl/analytics/
