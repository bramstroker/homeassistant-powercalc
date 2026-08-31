# Set-top box

Set-top boxes and streaming media players are represented by a Home Assistant `media_player` entity.

Profiles commonly use a fixed calculation strategy with a measured active power and standby power. When the
device offers multiple standby modes, define them as subprofiles so the user can select the configured mode.

## JSON

```json
{
  "calculation_strategy": "fixed",
  "device_type": "set_top_box",
  "fixed_config": {
    "power": 3.3
  },
  "standby_power": 0.3
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the
    [model structure](../structure.md).
