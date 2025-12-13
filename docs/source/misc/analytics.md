# Analytics & Telemetry

Powercalc can **optionally** send a small amount of **anonymous, aggregated usage data**. This helps us understand real-world usage and improve the integration over time.

This feature is **opt-in**, can be disabled at any time.

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

If you choose to enable it, you can disable it at any time in the Powercalc configuration.

---

## Data retention and access

We keep analytics data only as long as needed to support development and maintenance of Powercalc.

Access to the data is restricted to the Powercalc maintainer(s).

---

## Questions or concerns?

If you have questions about what is collected or why, please open a discussion or issue on the Powercalc GitHub repository.
