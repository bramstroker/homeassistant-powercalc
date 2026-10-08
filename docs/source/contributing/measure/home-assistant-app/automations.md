# Measurement automations

## Measure session status sensor

When both the Powercalc integration and the Measure app are running, Powercalc creates
`sensor.measure_session_status` after it receives the first status update from the app. The sensor is not created for
installations that do not use the Measure app.

The sensor reports the current session state, such as `idle`, `running`, `completed`, or `failed`. Its attributes
include the Measure app version and, when available, the session ID, controlled entity, and error message.
The `controlled_entity` attribute contains the Home Assistant entity ID controlled by the session, or a comma-separated
list for measurements controlling multiple lights. It remains available after the session finishes and is omitted for
measurements without a controlled Home Assistant entity. The sensor becomes unavailable when the app stops sending
status updates, for example when the app is stopped.

Use these examples in the Home Assistant automation editor's **Edit in YAML** view. Create a separate automation
for each example and adjust `sensor.measure_session_status` if your sensor has a different entity ID.

## Send a notification

Replace the notify action with the one for your device:

```yaml
alias: Notify when a Powercalc measurement completes
triggers:
  - trigger: state
    entity_id: sensor.measure_session_status
    to: "completed"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Powercalc measurement completed"
      message: >-
        Session {{ trigger.to_state.attributes.session_id }} has completed.
```

To notify on failure instead, change `to` to `"failed"` and adjust the notification text. The error is available as
`trigger.to_state.attributes.get('error', '')`.

## Flash the measured lights

The `controlled_entity` attribute (Measure app 0.7.0 or later) lets the automation target the lights from the
completed session, so you do not need to edit the automation when measuring a different light. The condition skips
sessions without a controlled light. Splitting the attribute on `, ` supports both one light and multiple lights.

```yaml
alias: Flash the measured lights when a Powercalc measurement completes
triggers:
  - trigger: state
    entity_id: sensor.measure_session_status
    to: "completed"
conditions:
  - condition: template
    value_template: >-
      {{ trigger.to_state.attributes.get('controlled_entity', '').startswith('light.') }}
actions:
  - action: light.turn_on
    target:
      entity_id: "{{ trigger.to_state.attributes.controlled_entity.split(', ') }}"
    data:
      flash: long
```

The light and its integration must support the [flash option](https://www.home-assistant.io/actions/light.turn_on/#options-in-yaml).
The duration and number of flashes depend on the device. Combine this with a notification if you may be away from
the room when the measurement finishes.
