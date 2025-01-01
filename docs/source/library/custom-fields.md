# Custom fields

Sometimes there is a need to ask the user to provide some additional data for a profile.
This can be done by adding custom fields to the profile configuration.
During discovery flow, or when user adds from library their will be an additional step where the user can provide the custom fields.

## Adding custom fields

You can add one or more custom fields to a profile by adding a `fields` section to the profile configuration.

```json
{
  "fields": {
    "switch_entity": {
      "label": "Switch entity",
      "description": "Select the switch entity for your device",
      "selector": {
        "entity": {
          "domain": "switch"
        }
      }
    }
  }
}
```

The key `switch_entity` is the key of the field. This can be referenced in the profile configuration using the `[[switch_entity]]` syntax.
After setup Powercalc will replace this with the value the user provided.

`label` is the label of the field that will be shown to the user.
`description` is optional and is shown to the user below the field.
`selector` is the type of field. The configuration is similar to [HA Blueprints](https://www.home-assistant.io/docs/blueprint/selectors/).

!!! note
    Not all selectors are tested. Some might not be supported. `number` and `entity` are tested and should work.

### Example number selector

In the example below we have a profile that asks the user to provide a number.
The profile then calculates the power usage based on the number provided.

```json
{
  "calculation_strategy": "fixed",
  "fields": {
    "num_switches": {
      "label": "Number of switches",
      "description": "Enter some number",
      "selector": {
        "number": {
          "min": 0,
          "max": 4,
          "step": 1
        }
      }
    }
  },
  "fixed_config": {
    "power": "{{ [[num_switches]] * 0.20 }}"
  }
}
```

When the user provides the number `2`, the template will be ``{{ 2 * 0.20 }}`` which will result in `0.40`.

### Example entity selector

In the example below we have a profile that asks the user to select a binary sensor.
The profile then calculates the power usage based on the state of the binary sensor.

```json
{
  "calculation_strategy": "composite",
  "fields": {
    "some_entity": {
      "label": "Some entity",
      "description": "Select some entity",
      "selector": {
        "entity": {
          "domain": "binary_sensor"
        }
      }
    }
  },
  "composite_config": [
    {
      "condition": {
        "condition": "state",
        "entity_id": "[[some_entity]]",
        "state": "on"
      },
      "fixed": {
        "power": 20
      }
    },
    {
      "fixed": {
        "power": 10
      }
    }
  ]
}

```
