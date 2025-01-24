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

## Excluding device types

You can exclude devices from being discovered by Powercalc by using the `exclude_device_types` option in the configuration.
For example, to exclude power meters and smart switches, when you are not interested in keeping track of self-consumption of these devices:

```yaml
powercalc:
  exclude_device_types:
    - power_meter
    - smart_switch
```

You can also use the GUI for this global configuration, see [Global Configuration](../configuration/global-configuration.md).
