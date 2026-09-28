# Measuring by device type

The Home Assistant Measure app first asks what you want to measure. Choose a device below, then the offered measurement method. **Free measurement** is for a single [average power reading](modes.md#average) or a [Playbook recording](modes.md#recorder); it does not create a device-specific profile automatically.

Before starting, connect the power meter so it measures the device described in the table. Disable automations or other controls that could change its state. The ready screen shows the instructions for your selected method and waits for you to press **Start**.

| Device | Method | What to measure |
| --- | --- | --- |
| [Light](lights.md) | Automated light measurement | PowerCalc changes the selected brightness, color temperature, color, or effects. |
| [Smart speaker](#smart-speaker) | Volume measurement | Playback power at different volume levels. |
| [Fan](#fan) | Automated speed measurement or experimental state recording | Percentage speeds, or manually selected states. |
| [Robot vacuum](#robot-vacuum) | Experimental vacuum and dock recording, or charging measurement | Dock activities and charging, or charging alone. |
| [Air purifier](#air-purifier) | Experimental state recording | Off and manual fan speeds. |
| [Camera](#camera) | Experimental state recording | Infrared off and on, when Home Assistant reports the difference. |
| [Heating](#heating) | Experimental state recording | Standby and observable heating levels. |
| [Printer](#printer) | Experimental state recording | Ready, printing, sleep, and other observable activities. |
| [Set-top box](#set-top-box) | Experimental state recording | Normal viewing and standby. |
| [Free measurement](#free-measurement) | Average or Playbook recording | One stable power value, or a complete power cycle to use manually. |

## Automated measurements

### Light

Select a `light` entity and the modes to measure. Disable automations and adaptive lighting before pressing **Start light measurement**. PowerCalc then controls the light through the chosen settings. Keep it powered and leave other controls alone until the run finishes. See [Light profiles](lights.md) for mode selection and measurement setup.

### Smart speaker

Select a `media_player` entity and disable automations that could change playback or volume. PowerCalc plays test audio and measures several volume levels, including high volume, so protect your hearing or move to another room before starting. If the speaker cannot play the automatic test stream, disable automatic streaming in setup and start a stable audio source yourself. See [Smart speaker measurement](modes.md#smart-speaker).

### Fan

For **Measure fan speeds**, select a percentage-controllable `fan` entity. Use manual speed mode and disable automations. Keep oscillation, direction, lights, and other extra functions at the same settings throughout the run. PowerCalc changes the fan speed automatically and measures the resulting power curve. See [Fan measurement](modes.md#fan).

### Robot vacuum

For **Measure charging power**, connect the complete dock at the wall outlet. Start the measurement before docking a robot with a low battery. Leave it charging without interruption through full charge and the following 30 minutes of trickle charging. Keep dock functions such as washing and drying off; this method measures charging, not cleaning or other dock activities. See [Charging measurement](modes.md#charging-device).

For **Record vacuum and dock activity**, use the [recording instructions](#robot-vacuum-and-dock-recording) below.

## Experimental device-state recordings

Select the primary Home Assistant entity that the generated profile should use. The recorder captures its state and scalar attributes. Add another signal only when its state explains a power change; the picker limits choices to the same device or its immediate parent or child device. The signal also needs a portable reference for a shared library profile. A camera requires a `camera` primary entity; a set-top box uses a `media_player` entity. See [Complex-profile recordings](modes.md#complex-profile-recordings) for the other entity requirements and analyser limits.

Start with the device powered and stable. Record each distinct state long enough for at least five power samples **after it settles**, return to the starting state, then stop. Use **Record more** for a second independent run covering the same states, again with at least five samples for every state. The analyser uses the earlier run for training and the latest run for validation. Recording longer cannot compensate for a missing Home Assistant state or attribute: check that the selected entities actually change when the power changes.

### Air purifier

Record off and each manual fan speed reported in Home Assistant. Disable automatic modes that can change speed during a sample. Keep the display, ionizer, and other extra functions fixed across both runs; this recording does not model their separate contributions.

### Camera

Use a `camera` primary entity. Check that its state or attributes, or a selected day/night or infrared entity, report whether infrared is off or on. Record both states and let power settle after each change. You may change the infrared setting or lighting conditions, but verify that the recorded signal follows the actual infrared state. Keep other camera settings fixed. Live viewing and video recording are not required measurement states; without an observable infrared signal, the analyser cannot build an infrared-dependent profile.

### Fan state recording

Choose **Record device states** if you need the fan's reported off and manual speed states instead of the automated percentage curve. Move through each reported speed and wait for stable power. Disable automatic speed changes, and keep oscillation, direction, lights, and other functions fixed in both runs. This recording models the selected state or speed, not combinations of those functions.

### Heating

Record standby and each heating power level that Home Assistant reports, such as numbered fan or heating modes. Wait for power to settle at each level. Check that the recorded states distinguish active heating from thermostat idle periods; changing only the target temperature does not prove which power level was active.

### Printer

Select the printer status entity that reports ready, printing, and sleep. Use the same representative print job in both runs, long enough to collect at least five power samples while printing. Include scanning or copying only when Home Assistant reports them as distinct states.

### Set-top box

Record normal viewing and standby. Allow startup and standby transitions to finish before counting stable samples. Check that the `media_player` entity reports the on and standby states correctly. Keep the energy-saving or standby setting unchanged in both runs.

If the box has energy-saving modes or a setting to enable or disable Wi-Fi that changes its power use, make a **separate measurement session for each configuration**. Keep that configuration fixed during both runs of its session; **Record more** within the same session is for validating the same settings. In your profile pull request, describe each setting and include the corresponding measurements. The app does not create subprofiles from these sessions yet, but the profile can be [assembled with subprofiles](../../library/sub-profiles.md) manually so users can select the configuration they use.

### Robot vacuum and dock recording

Select the `vacuum` entity and a numeric battery percentage sensor on the same Home Assistant device. The app can preselect other activity entities; review them and add relevant dock entities where available. Connect the **entire dock** at the wall outlet. Start recording before docking a low-battery robot or starting a cleaning trip. Include cleaning and the return to dock, plus auto-emptying, mop washing, drying, idle, and charging where supported. Let each activity complete and record charging over at least 20 battery percentage points, ideally until full and the dock returns to idle.

Use **Record more** for another complete cycle. Repeat every activity and charge over a similar battery range so the analyser can validate the profile on independent observations. See [Recording a vacuum and dock](modes.md#recording-a-vacuum-and-dock) for entity rules and analysis details.

## Free measurement

Choose **Measure average power** when you want one value for a stable device state. Put the device in that state before starting and leave it unchanged for the configured duration. Choose **Record a Playbook cycle** when you need power over time: start before the appliance cycle, let the complete cycle run, then stop recording. The Playbook CSV can be configured manually; see [Recorder](modes.md#recorder).
