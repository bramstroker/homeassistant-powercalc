# homeassistant-huepower
Custom component to calculate power consumption of hue lights

## Example configuration

```yaml
sensor:
  - platform: hue_power
    entity_id: light.hanglamp_boven
    name: "Hue lampje stroom"
```