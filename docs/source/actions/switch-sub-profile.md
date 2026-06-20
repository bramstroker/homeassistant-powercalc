# Switch Sub Profile

[![Open your Home Assistant instance and show your service developer tools with a specific action selected.](https://my.home-assistant.io/badges/developer_call_service.svg)](https://my.home-assistant.io/redirect/developer_call_service/?service=powercalc.switch_sub_profile)

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
