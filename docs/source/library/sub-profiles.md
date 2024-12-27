# Sub profiles

Some profiles might have multiple profiles. This is useful when a device has different power consumption based on the state of the device.
This can be used for example for different infrared modes of a light. Or lights having different effects.

Each sub profile has it's own subdirectory `{manufacturer}/{modelid}/{subprofile}`, which contains a `model.json` file.
You can also define `sub_profile_select` in the main `model.json` to automatically select the sub profile based on the state of the device.
When no `sub_profile_select` is defined, the user will be asked to select the sub profile during discovery or while setting up manually from library.

Examples:

- [lifx/LIFX A19 Night Vision](https://github.com/bramstroker/homeassistant-powercalc/tree/master/profile_library/lifx/LIFX%20A19%20Night%20Vision)
- [eufy/T8400](https://github.com/bramstroker/homeassistant-powercalc/tree/master/profile_library/eufy/T8400)

## Sub profile select

### Entity ID

```json
{
    "sub_profile_select": {
        "matchers": [
            {
                "type": "entity_id",
                "pattern": ".*_nightlight$",
                "profile": "nightlight"
            }
        ],
        "default": "default"
    }
}
```

## Entity state

```json
{
    "sub_profile_select": {
        "matchers": [
            {
                "type": "entity_state",
                "entity_id": "select.{{source_object_id}}_infrared_brightness",
                "map": {
                    "Disabled": "infrared_off",
                    "25%": "infrared_25",
                    "50%": "infrared_50",
                    "100%": "infrared_100"
                }
            }
        ],
        "default": "infrared_off"
    }
}
```

## Attribute

```json
{
    "sub_profile_select": {
        "matchers": [
            {
                "type": "attribute",
                "entity_id": "select.{{source_object_id}}_infrared_brightness",
                "map": {
                    "effect1": "effect1",
                    "effect2": "effect2"
                }
            }
        ],
        "default": "default"
    }
}
```

## Integration

```json
{
    "sub_profile_select": {
        "matchers": [
            {
                "type": "integration",
                "integration": "deconz",
                "profile": "deconz"
            }
        ],
        "default": "default"
    }
}
```
