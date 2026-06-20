# Other measure modes

The measure tool can also help with non-light profiles or one-off readings. These modes use the same power meter setup from [Setup](setup.md).

## Smart speaker

Use `Smart speaker` for media players where power consumption changes with playback and volume level.

Configuration:

```env
MEDIA_CONTROLLER=hass
HASS_URL=http://homeassistant.local:8123/api
HASS_TOKEN=your_long_lived_access_token
```

The wizard asks for the `media_player` entity. The runner measures volume levels from `10` through `100` in steps of `10`, then measures the muted or off state. By default it streams pink noise from a Powercalc-hosted URL during each volume measurement.

Some devices, such as Amazon Alexa devices, do not support direct streaming through this service call. In that case, choose the wizard option to disable automatic streaming and start a stable audio source manually.

The generated model uses a `linear` strategy with calibration points and a condition that enables calculation while the entity is playing.

!!! warning

    The smart speaker mode raises the volume up to 100 percent. Keep the speaker in a safe location and protect your hearing before starting.

## Fan

Use `Fan` for Home Assistant fan entities that support percentage control.

Configuration:

```env
FAN_CONTROLLER=hass
HASS_URL=http://homeassistant.local:8123/api
HASS_TOKEN=your_long_lived_access_token
```

The runner measures percentage values from `5` through `100` in steps of `5`. It waits after each percentage change, then takes an average measurement. It also measures standby after turning the fan off.

The generated model uses a `linear` strategy with percentage calibration points.

## Charging device

Use `Charging device` for devices where charging power can be mapped to battery level. The current device types are:

- `vacuum_robot`
- `lawn_mower_robot`

Configuration:

```env
CHARGING_CONTROLLER=hass
HASS_URL=http://homeassistant.local:8123/api
HASS_TOKEN=your_long_lived_access_token
```

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

Use `Recorder` to capture a power pattern for the [Playbook strategy](../../strategies/playbook.md). The runner writes a CSV file with elapsed time and measured power until you stop it with `CTRL+C`.

This is useful for:

- Recording program-based devices such as washing machines, dishwashers, and similar appliances.
- Capturing one full appliance cycle as a playbook CSV.
- Comparing different programs before configuring multiple playbooks.
- Checking whether a measurement duration is long enough.

Move the resulting CSV into the Home Assistant playbook directory and configure it as described in the [Playbook strategy documentation](../../strategies/playbook.md).
