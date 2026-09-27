# Variables

Powercalc library model.json files support the use of variables and custom fields to enhance flexibility and user customization.

## Built-in variables

You can use the following built-in variables in the `model.json` file.

`[[entity]]`: The entity ID of the entity for which the power sensor is being created.

`[[entity_by_device_class:{device_class}]]`: Finds an entity with the specified device class, preferring the same device as `[[entity]]`.
For example, `[[entity_by_device_class:temperature]]` will find a temperature sensor in the same device, and `[[entity_by_device_class:battery]]` will find a battery sensor.

`[[entity_by_translation_key:{translation_key}]]`: Finds an entity with the specified translation key, preferring the same device as `[[entity]]`.
This is useful when an integration exposes multiple related entities for one device and the profile needs to reference one of them without asking the user to configure an extra entity manually.

For example, NUT UPS entities can expose translation keys such as `ups_load` and `ups_power_nominal`:

```json
{
  "calculation_strategy": "fixed",
  "fixed_config": {
    "power": "{{ states('[[entity_by_translation_key:ups_load]]') | float(0) / 100 * states('[[entity_by_translation_key:ups_power_nominal]]') | float(0) * 0.7 }}"
  }
}
```

### Related-device lookup

Both placeholders search enabled entities on the source device first. If multiple entities on that device match, the first match is used.
If there is no match, Powercalc searches:

- Native child devices whose `parent_device_id` is the source device, on Home Assistant versions that support child devices.
- Roborock docks whose identifier is the source's Roborock identifier plus `_dock`, within the same integration config entry.

The fallback must find exactly one matching entity. If several entities match, Powercalc logs the candidates and leaves the placeholder unresolved, so profile setup cannot silently select the wrong entity.
Disabled entities are excluded from both searches. Shared config-entry membership alone does not establish a relationship, and Powercalc does not search parents, siblings, or devices connected through `via_device_id`.

For example, a Roborock profile can reference the dock's active drying switch in a composite condition:

```json
{
  "condition": "state",
  "entity_id": "[[entity_by_translation_key:mop_drying]]",
  "state": "on"
}
```

The `_dock` identifier rule is specific to the Roborock integration. Other integrations may expose dock entities directly on the vacuum device or as native child devices.

## Custom fields

Sometimes there is a need to ask the user to provide some additional data for a profile.
This can be done by adding custom fields to the profile configuration.
During discovery flow, or when user adds from library their will be an additional step where the user can provide the custom fields.

### Adding custom fields

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

#### Automatically selecting an entity

From Powercalc v1.26.0, an entity field can use `auto_select` to prefill its selector:

```json
{
  "fields": {
    "floodlight_entity": {
      "label": "Spotlight light",
      "selector": {
        "entity": {
          "domain": "light"
        }
      },
      "auto_select": {
        "integration": "tapo_control",
        "unique_id_pattern": "-floodlight\\(timed\\)$"
      }
    }
  }
}
```

Use `translation_key` when the integration supplies one, for example
`"auto_select": {"translation_key": "ups_load"}`. For integrations without translation keys,
`unique_id_pattern` searches the entity registry's unique ID using a regular expression, independently of the
user-assigned entity ID or display name. Verify the pattern against the integration's entity implementation.
Use `^floodlight` for a prefix, `floodlight$` for a suffix, or `^floodlight$` for an exact match.
Without anchors, the pattern can match anywhere in the unique ID. Escape literal regex characters,
and double backslashes in JSON, as shown for the parentheses above. Invalid regexes are rejected by profile validation.
`integration` optionally restricts the providing integration. All supplied criteria must match,
and matching is case-sensitive. At least one of `translation_key` or `unique_id_pattern` is required.

Powercalc selects an entity only when exactly one enabled entity on the source device matches.
The selector's domain, integration, device class, inclusion and exclusion filters still apply.
Domain, integration and device class also work inside `filter`, including lists of alternative filters. Filters requiring
other data, such as supported features or device properties, are left for manual selection.
Missing device context, missing entities and ambiguous matches leave the field unselected.
Only single-entity selectors support `auto_select`.

The form remains editable. An explicit field `default` takes precedence over automatic selection,
and saved field values take precedence over both. This feature only prefills the configuration form;
YAML configurations still need to supply their `variables` explicitly.

#### Example number selector

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

#### Scaling per-unit measurements

Profiles with measurements for one panel, strip segment, or bulb can use a custom field as their default `multiply_factor`.
This also works with LUT profiles, whose CSV values cannot contain placeholders.

```json
{
  "min_version": "v1.26.0",
  "multiply_factor": "[[panel_count]]",
  "standby_power_on": 1.6,
  "fields": {
    "panel_count": {
      "label": "Number of panels",
      "description": "Number of light panels connected to the controller",
      "selector": {
        "number": {
          "min": 1,
          "max": 500,
          "step": 1
        }
      }
    }
  }
}
```

This fragment multiplies calculated power by the panel count, then adds the controller's 1.6 W once.
The LUT must contain per-panel power with the controller's consumption already removed.
Standby power is multiplied only when the user enables `multiply_factor_standby`.
An explicit sensor `multiply_factor` overrides the profile default.

The profile value can also be a literal number. After field substitution, it must be a finite number.
Set `min_version` to `v1.26.0` or higher so older Powercalc versions skip profiles using this option.

#### Example entity selector

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

### Defining variables for YAML sensors

When defining a profile for YAML sensors, you can pass the required variables this way:

```yaml
powercalc:
  sensors:
    - entity_id: light.your_light_entity
      manufacturer: "some_manufacturer"
      model: "some_model"
      variables:
        switch_entity: switch.your_switch_entity
```
