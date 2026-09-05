# Using and contributing measurement results

After a measurement, review the result and decide whether you want to use it privately or contribute it to the shared Powercalc profile library. A contributed profile helps other users with the same device.

The measure tool creates a strong starting point, but you are still responsible for checking that the device identification and measured values are plausible.

## Download from the Home Assistant app

The result page shows the measured summary, available plots, and generated files.

1. Review the plots for unexpected gaps, spikes, or values that do not match the device behavior.
2. Select **Download all** to save the complete output, or download individual files when you only need part of the result.
3. Extract the downloaded archive on your computer.
4. Keep the diagnostics download separately. Diagnostics are useful for issue reports, but do not belong in a power profile pull request.

Some measurement types only produce a value or a recording:

- **Average** shows the measured average power. Use this value when creating a fixed-power profile or configuring Powercalc manually.
- **Recorder** produces either a headerless two-column Playbook CSV or an experimental complex-profile JSON Lines (`.jsonl`) recording. A complex recording also produces `analysis.json`; when one state or scalar attribute credibly explains the power, it produces a fixed `states_power` `model.json`. The source recording is retained when there is not enough evidence, and composite model generation is not supported yet.

## Find CLI output

When using the CLI with Docker, output is written to the mounted `export` directory in the measurement working directory:

```text
powercalc-measure/
  .env
  export/
    <model_id>/
      model.json
      brightness.csv.gz
      color_temp.csv.gz
```

Native CLI runs write to:

```text
utils/measure/export/
```

## Understand the generated files

Lookup-table measurements can create CSV files for brightness, color temperature, color, white, or effect modes. Linear measurements store their calibration in `model.json`.

Experimental complex-profile recorder sessions keep three distinct artifacts:

- `record.jsonl` is the original typed metadata and sample stream;
- `analysis.json` records the winning strategy and validation evidence, or why no model was created;
- `model.json` is present only when the analyser accepts a fixed `states_power` candidate.

When model generation is enabled, `model.json` contains available metadata such as:

- `name` and `device_type`;
- `calculation_strategy` and its configuration;
- `standby_power`;
- `measure_method`, `measure_device`, and measurement settings;
- `created_at`;
- `min_voltage` and `max_voltage` when voltage readings are available.

Information the tool cannot determine may still need to be added, including:

- product aliases or additional discovery identifiers;
- a new `manufacturer.json` when the manufacturer is not yet in the library;
- device-specific metadata that cannot be read from Home Assistant.

## Prepare the profile directory

Profiles belong under:

```text
profile_library/<manufacturer>/<model>/
```

Use the exact model identifier for the model directory, not the full marketing name. Set `name` in `model.json` to the marketed product name without repeating the manufacturer. For example, a Signify profile should use `Hue White Ambiance GU10`, not `Signify Hue White Ambiance GU10`. Reserve `aliases` for additional model identifiers that can discover the same hardware.

For example:

```text
profile_library/acme/LED1837R5/
  model.json
  hs.csv.gz
  color_temp.csv.gz
```

If the manufacturer does not exist yet, also add:

```text
profile_library/acme/manufacturer.json
```

!!! important
    Never edit or include `profile_library/library.json`. It is generated automatically.

## Contribute from the Home Assistant app

Completed light, speaker, fan, and charging measurements that generated a valid `model.json` can prepare and open a pull request directly from the result page.

1. Open **Settings → GitHub** in Powercalc Measure.
2. Connect your GitHub account with the device login, or supply a personal access token with public-repository access.
3. Return to the completed measurement and select **Create pull request automatically**.
4. Confirm the manufacturer and model details. For an existing manufacturer, follow the library link and compare the product naming and metadata with its other profiles.
5. Review the exact files, generated JSON, commit message, and pull-request text.
6. Select **Create pull request** only after the preview is correct.

The app reuses your existing fork or creates one when needed. It then creates a focused branch and commit and opens a pull request against Powercalc. An existing profile with the same manufacturer and model is not replaced automatically; use the manual process when proposing an update.

GitHub credentials are stored in the app's private data so the connection can be configured before measuring and reused. Home Assistant may include that data in app backups. Disconnect the account from Powercalc Measure and revoke the authorization in GitHub when it is no longer needed.

The automatic workflow is optional. Downloading the files and contributing manually always remains available, including when GitHub is not configured or automatic contribution is blocked.

## Create a pull request with GitHub Desktop

This route does not require command-line Git.

1. Sign in to GitHub and [fork the Powercalc repository](https://github.com/bramstroker/homeassistant-powercalc/fork).
2. Install [GitHub Desktop](https://desktop.github.com/) and clone your fork.
3. In GitHub Desktop, create a branch with a descriptive name such as `profile/acme-led1837r5`.
4. Open the cloned repository folder on your computer.
5. Copy the prepared manufacturer and model files into the correct `profile_library` directory.
6. Review the changes in GitHub Desktop. Ensure that only files for this device are included.
7. Enter a short commit message, commit the changes, and select **Publish branch**.
8. Select **Create Pull Request**. The browser opens the Powercalc pull request form.
9. Follow the [power profile pull request template](https://github.com/bramstroker/homeassistant-powercalc/blob/master/.github/PULL_REQUEST_TEMPLATE/power_profile.md) and submit the pull request against the Powercalc `master` branch.

GitHub runs automatic profile validation after the pull request is opened. If a check fails, open its details to see the filename and validation message, then correct the file in your branch.

## Create a pull request with Git

If you already use Git, create a branch in your fork, copy the profile, and push it:

```bash
git switch -c profile/acme-led1837r5
git add profile_library/acme/LED1837R5
git commit -m "feat(profile): add Acme LED1837R5"
git push --set-upstream origin profile/acme-led1837r5
```

Open the link printed by `git push`, create the pull request against Powercalc `master`, and use the power profile template.

## Final review checklist

Before submitting, confirm that:

- the manufacturer and exact model identifier are correct;
- the product name does not repeat the manufacturer;
- the model directory uses the model ID rather than a generic family or marketing name;
- `measure_device` uses an existing library value when the same meter is already listed;
- `model.json` describes the measured product and calculation strategy correctly;
- generated CSV files match the capabilities and modes of the device;
- compressed `.csv.gz` files do not have uncompressed `.csv` duplicates;
- standby power is realistic and was not recorded as `0` because of meter limitations;
- only the profile and, when necessary, `manufacturer.json` are included;
- diagnostics, screenshots, temporary files, and `library.json` are not included;
- the pull request explains unusual setup details such as a dummy load, multiple lights, OCR, manual readings, or estimated standby power.

Submit one device per pull request. Small, focused pull requests are easier to validate and review.
