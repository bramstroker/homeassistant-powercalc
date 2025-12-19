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
- Powercalc version and Home Assistant version

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
        }
      },
      "ha_version": "2025.10.0.dev0",
      "install_id": "081ac191-2667-4242-8226-ecc66b1f7e9e",
      "group_size_max": 2,
      "group_size_min": 2,
      "powercalc_version": "0.1.1",
      "config_entry_count": 8,
      "custom_profile_count": 12,
      "has_global_gui_config": true
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
