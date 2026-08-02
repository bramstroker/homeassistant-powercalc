# Discovery

During startup, Powercalc will scan your Home Assistant installation for entities and devices that match the library profiles.
Only entities which have a device attached will be considered for discovery.
Device information can be viewed at the top left corner of the device page in the Home Assistant UI, or in `config/.storage/core.device_registry`.

Each device in HA has the following properties:

- manufacturer
- model
- model_id (optional)

This information is tried to match again the built-in library and your custom model directory.
When a match in custom models is found, the built-in library loading is skipped.

starting with the manufacturer. Both manufacturer name and aliases are matched.
If a match is found, the model id is matched. Both the directory_name (model id) and additional aliases (from model.json) are matched.

You can enable [debug logging](../troubleshooting/debug-logging.md) to debug the matching process.

## Devices with a generic model identifier

Some devices do not report a model that identifies the actual hardware.
This is common for white label products built on a shared chipset, where dozens of brands ship different hardware under one identifier.

Well known examples are the Tuya identifiers `TS0011`, `TS0505B`, `TS0502A` and `TS0601`.
A device reporting `TS0011` in Zigbee2MQTT can be a wall switch, a switch module, a DIN rail relay or even a water valve, depending on the manufacturer.
Power consumption between these devices differs greatly, so a single profile cannot describe them.

For this reason Powercalc does not add profiles for generic identifiers to the library, and does not add them as an alias on a branded profile.
Doing so would create discoveries with wrong power values for everyone owning a different device with the same identifier.
See the [contribution requirements](../contributing/measure/index.md) for the full rule.

For the same reason discovery may not find a profile for your device, even when the library contains measurements for the exact product you own.
The profile is stored under the real brand, while your device reports the generic manufacturer of the chipset vendor.
In that case configure the sensor manually.

### Select a library profile manually

When the library contains a profile for your device, point Powercalc at it directly.
In the GUI select `Virtual power (library)`, in YAML specify the manufacturer and model:

```yaml
powercalc:
  sensors:
    - entity_id: switch.my_switch
      manufacturer: bseed
      model: zigbee_switch_1_gang_no_neutral
```

See [virtual power sensor (library)](../sensor-types/virtual-power-library.md) for more information.

## Discovery configuration

Powercalc includes several global configuration options that let you fine-tune the behavior of the discovery routine.

You can manage them with YAML using the `powercalc->discovery` key.
Or use the GUI, see [Global Configuration](../configuration/global-configuration.md).

### Disable autodiscovery

Discovery is enabled by default.
If you want to turn it off entirely, use the following configuration:

```yaml
powercalc:
  discovery:
    enabled: false
```

### Excluding device types

You can exclude devices from being discovered by Powercalc by using the `exclude_device_types` option in the configuration.
An overview of possible device types can be found [here](device-types/index.md).

```yaml
powercalc:
  discovery:
    exclude_device_types:
      - power_meter
      - cover
```

### Excluding self-usage

Many smart switches with power monitoring do not report their own internal consumption.
Powercalc includes power profiles to estimate this self-usage, but not everyone finds these sensors useful, especially when you have many switches, as they can create a lot of extra discoveries.

You can disable self-usage profiles with:

```yaml
powercalc:
  discovery:
    exclude_self_usage: true
```
