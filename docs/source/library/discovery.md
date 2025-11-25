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
