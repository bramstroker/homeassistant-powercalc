
# Library Structure

The library follows a multi-level tree structure:

- **Top level**: Manufacturer
- **Second level**: Model ID
- **Optional**: Sub-profiles for specific device behaviors

Each **manufacturer directory** must include a `manufacturer.json` file. This file should contain the manufacturer's name and optionally a list of aliases.

Each **device profile** resides in its own subdirectory:
`{manufacturer}/{modelid}` (e.g., `signify/LCT010`)
This directory contains a mandatory `model.json` file and, optionally, CSV files used for LUT (Look-Up Table) calculation strategies.

## `model.json`

Every device profile **must** include a `model.json` file, which defines supported calculation modes and other configuration parameters.
Refer to the [JSON schema](https://github.com/bramstroker/homeassistant-powercalc/blob/master/profile_library/model_schema.json) for full details.

### Required Fields

- `name`: The device name (used only for display in the [Library](https://library.powercalc.nl)).
- `device_type`: The type of device. See [Device Types](device-types/index.md) for details.
- `calculation_strategy`: Strategy used for power calculation. See [Calculation Strategies](../strategies/index.md).
- `measure_method`: Method used for power measurement. Options: `manual` or `script`.
- `measure_device`: The measuring device (e.g., `Shelly PM Gen 3`).
- `created_at`: Date the profile was created (ISO 8601 format, e.g., `2023-06-19T08:02:31`).
- `author`: Author of the profile.

### Discovery Behavior

By default, Powercalc performs discovery on a **per-entity** basis. This can cause issues if a device has multiple entities, resulting in multiple discoveries.

To avoid this, you can set:

```json
"discovery_by": "device"
```

This enables **per-device** discovery, which is more reliable.
It is especially recommended for device types using `sensor` domain entities: [network](device-types/network.md), [power_meter](device-types/power-meter.md), and [generic_iot](device-types/generic-iot.md).

---

## Aliases and Linked Profiles

- Use `aliases` to define alternative model names for discovery.
  This is helpful when the same device is reported differently across integrations (e.g., Hue vs. deCONZ).

!!! note

    When using `aliases`, only discovery information is added to the **existing** profile in the library.

- Use `linked_profile` to point to another profile that contains the measurement data.
  This creates a **separate** entry in the library.

  Format: `manufacturer/modelid`
  Example: `signify/LCT010`

---

## Sub-Profiles

Some devices may have different power usage based on their state.
In these cases, you can define multiple sub-profiles within the same model.

See [Sub Profiles](sub-profiles.md) for details.
