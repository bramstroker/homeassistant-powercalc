# Network

Generic device type for network devices. Can be used for routers, switches, access points, etc.

## JSON

```json
{
  "device_type": "network",
  "discovery_by": "device",
  "calculation_strategy": "fixed",
  "fixed_config": {
    "power": 3.0
  }
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the [model structure](../structure.md)

When the device is always on and you don't want powercalc virtual sensor to bind to an entity you can use the following config:
