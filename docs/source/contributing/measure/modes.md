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
- **Data for a complex power profile (experimental)** records power together with the state and attributes of selected Home Assistant entities. Vacuum recordings filter attributes as described below. Generic devices can produce fixed profiles from one state or scalar attribute. The vacuum recipe can produce activity-based composite profiles with battery charging calibration when repeated episodes provide sufficient evidence.

The CLI always creates a Playbook CSV and stops when you press `CTRL+C`. The app stops the recorder from the running-session screen.

This is useful for:

- Recording program-based devices such as washing machines, dishwashers, and similar appliances.
- Capturing one full appliance cycle as a playbook CSV.
- Comparing different programs before configuring multiple playbooks.
- Checking whether a measurement duration is long enough.

### Complex-profile recordings

Choose **Generic device** to track one or more entities from any Home Assistant domain.

Choose **Robot vacuum** for guided entity selection and dock activity analysis. See [Recording a vacuum and dock](#recording-a-vacuum-and-dock) below for setup and analysis requirements.

Complex recordings use JSON Lines (`.jsonl`). The first record describes the recording and selected entities; every following sample contains a power reading and entity map. This lets the recorder stream samples safely without holding the complete recording in memory:

```json
{"record_type":"metadata","format_version":1,"recipe":"vacuum_robot","primary_entity_id":"vacuum.robot","entities":[{"entity_id":"vacuum.robot","domain":"vacuum","role":"primary"},{"entity_id":"sensor.robot_battery","domain":"sensor","role":"battery"}]}
{"record_type":"sample","elapsed_seconds":0.0,"power":4.2,"entities":{"vacuum.robot":{"state":"cleaning","attributes":{"battery_level":42}},"sensor.robot_battery":{"state":"42","attributes":{"unit_of_measurement":"%"}}}}
```

Stopping the recording starts analysis automatically. The result includes `analyser.json`. A `model.json` is added only when the candidate covers at least 90% of validation samples and improves mean absolute error enough over a constant-power baseline. Each learned value needs at least five recorded samples. Vacuum analysis additionally holds out whole episodes and checks error and coverage for every activity, so a long idle period cannot hide a bad short dock cycle. If those checks fail, the recording still completes and explains what additional evidence is needed.

Because this includes entity attributes, inspect the file for installation-specific or sensitive values before sharing it.
While recording, the measurement screen shows the latest state of every tracked entity beneath the live power chart. Recorded attributes remain in the JSON Lines file rather than the live view.

For a Playbook recording, move the resulting CSV into the Home Assistant playbook directory and configure it as described in the [Playbook strategy documentation](../../strategies/playbook.md).

### Recording a vacuum and dock

Choose **Recorder**, **Complex profile**, and **Robot vacuum**. Select the vacuum and its battery percentage
sensor. The battery sensor must belong to the same Home Assistant device; the app selects it automatically when
exactly one usable sensor is available. The app preselects the other enabled entities with live states on that device. You can
remove entities or add dock entities belonging to another device. Camera and image entities are not selected
automatically. Changing the selected vacuum resets these defaults; reopening a saved configuration preserves your
selections.

Measure the entire dock at the wall outlet. Start with a low battery and record charging through completion,
idle, cleaning, mop washing, auto-emptying, and drying where supported. Repeat cycles to allow validation against
independent runs rather than nearby samples from the same cycle.

The selected entity list is fixed for the run. `record.jsonl` includes entity roles, integration, translation keys,
device classes, units, and device associations when available. Its device inventory also lists disabled entities
without recording their states or enabling them. Enable any useful missing entities in Home Assistant before
starting a new recording.

Vacuum recordings keep bounded scalar attributes, omitting nested payloads, long strings, URL values, and common
network, location, and credential attributes. The metadata describes this filtering policy. Recordings still contain
entity IDs and other device data: review them before sharing. If an optional entity disappears, its state is recorded
as `unavailable`, with a warning, while power readings continue. Missing required vacuum or battery entities cause
that sample to be skipped.

Automatic analysis is experimental. The generic recipe still fits one state or scalar attribute with a fixed
`states_power` model. The vacuum recipe can generate a small `stop_at_first` composite profile: measured dock
activities use fixed power, and charging uses a battery-level calibration curve.

Repeat every observed activity in at least two independent episodes, with at least five samples per episode.
Record washing, drying, auto-emptying, charging, sleep/standby, and operation away from the dock where supported.
Capture continuous charging over at least 20 battery percentage points. A single run is useful source data but
does not provide independent evidence for automatic profile generation.

The analyser uses recognised runtime status sensors or active activity flags, not settings such as an
**auto drying enabled** switch. Related entities need unambiguous same-device registry metadata to produce portable
profile placeholders. For older recordings, matching `battery_level` attributes can supply charging data.
Unrecognised modes or unreliable overlaps cause a request for more data; the analyser does not infer an additive
charging-plus-drying model or insert an unmeasured zero-power fallback.

Validation holds out whole episodes rather than nearby samples from the same episode. The analyser's Python API
also accepts several compatible recording paths and prefers a whole held-out recording when it contains every
observed activity. The app currently analyses its session's single recording. Inspect `analyser.json` for per-activity
coverage, typical and transition errors, and measured versus predicted energy. Energy is integrated only across
adjacent covered validation samples, without bridging gaps or activity boundaries. Generated profiles still need
contributor testing before submission.
