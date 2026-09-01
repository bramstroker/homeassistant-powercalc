# Other measure modes

The measure tool can also help with non-light profiles or one-off readings. All these modes are available in both the [Home Assistant app](home-assistant-app.md) and the [CLI](setup.md), and use the same power meter setup.

## Smart speaker

Use `Smart speaker` for media players where power consumption changes with playback and volume level.

=== "Home Assistant app"

    Select the `media_player` entity when creating the measurement session.

=== "CLI"

    ```env
    MEDIA_CONTROLLER=hass
    ```

    The Home Assistant connection is configured once in your `.env`; see [Home Assistant configuration](setup.md#home-assistant-configuration). The wizard asks for the `media_player` entity.

The runner measures volume levels from `10` through `100` in steps of `10`, then measures the muted or off state. By default it streams pink noise from a Powercalc-hosted URL during each volume measurement.

Some devices, such as Amazon Alexa devices, do not support direct streaming through this service call. In that case, choose the wizard option to disable automatic streaming and start a stable audio source manually.

The generated model uses a `linear` strategy with calibration points and a condition that enables calculation while the entity is playing.

!!! warning

    The smart speaker mode raises the volume up to 100 percent. Keep the speaker in a safe location and protect your hearing before starting.

## Fan

Use `Fan` for Home Assistant fan entities that support percentage control.

=== "Home Assistant app"

    Select the `fan` entity when creating the measurement session.

=== "CLI"

    ```env
    FAN_CONTROLLER=hass
    ```

    The wizard asks for the `fan` entity.

The runner measures percentage values from `5` through `100` in steps of `5`. It waits after each percentage change, then takes an average measurement. It also measures standby after turning the fan off.

The generated model uses a `linear` strategy with percentage calibration points.

## Charging device

Use `Charging device` for devices where charging power can be mapped to battery level. The current device types are:

- `vacuum_robot`
- `lawn_mower_robot`

=== "Home Assistant app"

    Select the `vacuum` or `lawn_mower` entity when creating the measurement session.

=== "CLI"

    ```env
    CHARGING_CONTROLLER=hass
    ```

    The wizard asks for the `vacuum` or `lawn_mower` entity.

Start with the device as close to empty as possible. The runner waits for charging to start, records power readings while the battery level rises, and then measures trickle charging at 100 percent.

The battery level can come from either:

- An attribute on the main entity, usually `battery_level`.
- A separate sensor entity.

The generated model uses a `linear` strategy with battery-level calibration points and enables calculation while the entity is docked.

## Average

Use `Average` when you need a single average power reading for a device state.

The wizard asks for a duration in seconds. After you press enter, the tool reads the power meter for that duration and prints the average result. This mode does not create a full profile by itself, but it is useful when you manually build a `fixed` profile or need a reliable value for a specific state.

Examples:

- Printer idle power.
- Camera day mode or night mode.
- Smart switch self-usage in `on` and `off` states.
- Network device idle power.

## Recorder

Use `Recorder` to capture an open-ended power time series. In the Home Assistant app, first choose what the recording is for:

- **A Playbook CSV** writes the existing headerless `elapsed time,power` format used by the [Playbook strategy](../../strategies/playbook.md).
- **Data for a complex power profile** records power together with the state and complete attributes of selected Home Assistant entities. This produces source data for later profile development; it does not analyze the recording or generate a profile.

The CLI always creates a Playbook CSV and stops when you press `CTRL+C`. The app stops the recorder from the running-session screen.

This is useful for:

- Recording program-based devices such as washing machines, dishwashers, and similar appliances.
- Capturing one full appliance cycle as a playbook CSV.
- Comparing different programs before configuring multiple playbooks.
- Checking whether a measurement duration is long enough.

### Complex-profile recordings

Choose **Generic device** to track one or more entities from any Home Assistant domain.

Choose **Robot vacuum** for a guided recording. Select the `vacuum` entity and its battery percentage sensor. The battery sensor must belong to the same Home Assistant device; the app selects it automatically when exactly one usable sensor is available. You can add other entities, including dock controls or status sensors, without having them selected automatically.

Measure the complete dock or base station at the wall outlet. Start with a low battery and capture charging, idle, and cleaning. Also capture washing, drying, and dust-emptying when the dock supports those operations.

Complex recordings use JSON Lines (`.jsonl`): every sample is stored as one complete JSON object containing the power reading and an entity map. This lets the recorder stream samples safely without holding the complete recording in memory:

```json
{"elapsed_seconds":0.0,"power":4.2,"entities":{"vacuum.robot":{"state":"cleaning","attributes":{"battery_level":42}},"sensor.robot_battery":{"state":"42","attributes":{"unit_of_measurement":"%"}}}}
```

Because this includes complete entity attributes, inspect the file for installation-specific or sensitive values before sharing it.
While recording, the measurement screen shows the latest state of every tracked entity beneath the live power chart. Complete attributes remain in the JSON Lines file rather than the live view.

For a Playbook recording, move the resulting CSV into the Home Assistant playbook directory and configure it as described in the [Playbook strategy documentation](../../strategies/playbook.md).
