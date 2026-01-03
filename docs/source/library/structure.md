
# Library Structure

The library follows a multi-level tree structure:

- **Top level**: Manufacturer
- **Second level**: Model ID
- **Optional**: Sub-profiles for specific device behaviors

Each **manufacturer directory** must include a `manufacturer.json` file. This file should contain the manufacturer's name and optionally a list of aliases.

Each **device profile** resides in its own subdirectory:
`{manufacturer}/{modelid}` (e.g., `signify/LCT010`)
This directory contains a mandatory `model.json` file and, optionally, CSV files used for [LUT (Look-Up Table)](../strategies/lut.md) calculation strategy.

## `model.json`

Every device profile **must** include a `model.json` file, which defines supported calculation modes and other configuration parameters.
Refer to the [JSON schema](https://github.com/bramstroker/homeassistant-powercalc/blob/master/profile_library/model_schema.json) for full details.

### Available Fields

Below is a comprehensive table of all fields that can be used in a `model.json` file:

| Field                             | Type             | Required | Description                                                                                                                             |
|-----------------------------------|------------------|----------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `name`                            | string           | Yes | The full name of the device (used only for display in the [Library](https://library.powercalc.nl))                                      |
| `device_type`                     | string           | Yes | Type of device (e.g., light, camera, fan). See [Device Types](device-types/index.md) for implementation examples                        |
| `calculation_strategy`            | string           | Yes | Strategy used for power calculation (lut, linear, fixed, multi_switch, composite). See [Calculation Strategies](../strategies/index.md) |
| `measure_method`                  | string           | Yes | How the device was measured (manual, script)                                                                                            |
| `measure_device`                  | string           | Yes | Device which was used to measure (e.g., `Shelly PM Gen 3`)                                                                              |
| `created_at`                      | string           | Yes | Creation date of the profile (ISO 8601 format, e.g., `2023-06-19T08:02:31`)                                                             |
| `author`                          | string           | Yes | Author of the profile                                                                                                                   |
| `aliases`                         | array of strings | No | Alternative model id's for this model, used for discovery purposes                                                                      |
| `calculation_enabled_condition`   | string           | No | Template which can be evaluated to determine if calculation is enabled                                                                  |
| `composite_config`                | object/array     | No | Configuration for [composite](../strategies/composite.md) calculation strategy                                                          |
| `config_flow_discovery_remarks`   | string           | No | Remarks to show in the GUI config flow on first step of discovery                                                                       |
| `config_flow_sub_profile_remarks` | string           | No | Remarks to show in the GUI config flow on sub profile selection step                                                                    |
| `description`                     | string           | No | A short description of the device                                                                                                       |
| `discovery_by`                    | string           | No | Whether to discover the profile by device or entity                                                                                     |
| `fields`                          | array of objects | No | Custom fields for the profile, more about it explained in [Variables](variables.md)                                                     |
| `fixed_config`                    | object           | No | Configuration for [fixed](../strategies/fixed.md) calculation strategy                                                                  |
| `is_dumb_bulb`                    | boolean          | No | Indicates if the profile is for a dumb light bulb without smart capabilities                                                            |
| `linear_config`                   | object           | No | Configuration for [linear](../strategies/linear.md) calculation strategy                                                                |
| `linked_profile`                  | string           | No | Use data from another model                                                                                                             |
| `measure_description`             | string           | No | Additional information about how the device was measured                                                                                |
| `measure_device_firmware`         | string           | No | Firmware version of the device used to measure                                                                                          |
| `measure_settings`                | object           | No | Settings used for measure script, for future reference                                                                                  |
| `min_version`                     | boolean          | No | Minimum required Powercalc version for the profile                                                                                      |
| `only_self_usage`                 | boolean          | No | Indicates if profile only provides power usage for the device itself                                                                    |
| `playbook_config`                 | object           | No | Configuration for [playbook](../strategies/playbook.md) calculation strategy                                                            |
| `sensor_config`                   | object           | No | Sensor configuration options. See [Sensor configuration](../configuration/sensor-configuration.md)                                      |
| `standby_power`                   | number           | No | Power draw when the device is turned off                                                                                                |
| `standby_power_on`                | number           | No | Power draw when the device is turned on                                                                                                 |
| `sub_profile_select`              | object           | No | Configuration to automatically select a sub profile, see [sub profiles](sub-profiles.md)                                                |

#### Calculation Strategy Specific Fields

Depending on the `calculation_strategy` you choose, you'll need to provide specific configuration:

##### Fixed Strategy (`fixed_config`)
```json
"fixed_config": {
  "power": 5.0,  // Fixed power value in watts
  "states_power": {  // Optional: power values for different states
    "idle": 2.0,
    "playing": 5.0,
    "off": 0.5
  }
}
```

##### Composite Strategy (`composite_config`)
Allows combining multiple calculation strategies based on conditions:

```json
"composite_config": {
  "mode": "stop_at_first",  // or "sum_all"
  "strategies": [
    {
      "condition": {
        "condition": "state",
        "entity_id": "light.example",
        "state": "on"
      },
      // Strategy-specific config here
    }
  ]
}
```

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
