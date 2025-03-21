# Switch Sub Profile

Switch the sub profile for a given entity while HA is running.
This is only applicable for sensors which have multiple sub profiles.

## Example

```yaml
action: powercalc.switch_sub_profile
data:
  profile: length_5
target:
  entity_id: sensor.my_light_power
```
