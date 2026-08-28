---
name: power-profile-pr-reviewer
description: Review pull requests that add or modify PowerCalc power profiles under profile_library. Use for validating profile schema and repository conventions, checking calculation-strategy data and measurement credibility, comparing similar profiles, and producing concise, actionable review feedback.
---

# SKILL: PowerCalc Power Profile PR Reviewer

## Skill ID
powercalc.profile_pr_reviewer

## Description
This skill reviews pull requests that add or modify **power profiles** in the PowerCalc `profile_library`. It validates schema correctness, repository conventions, measurement credibility, and overall profile quality.

The goal is to help maintain a **consistent, reliable, and high‑quality profile library** while keeping feedback friendly and actionable for contributors.

## When This Skill Should Be Used
Use this skill whenever a pull request modifies files under:

```
profile_library/
```

Typical cases include:

- New model profile
- Updates to `model.json`
- LUT additions or corrections
- Metadata fixes
- Strategy corrections
- Schema migrations

## Inputs

The skill expects:

- Pull request diff
- Modified files under `profile_library/`
- Relevant `model.json` and `manufacturer.json`
- Associated LUT or auxiliary files
- PR device information, including the integration through which Home Assistant reported the manufacturer and model

## Repository Assumptions

The following conventions apply to the PowerCalc repository:

- `profile_library/library.json` is **auto‑generated** and must never be edited manually
- `profile_library/model_schema.json` defines the expected schema for `model.json`
- Manufacturer and model directories follow:

```
profile_library/<manufacturer>/<model>/
```

Example:

```
profile_library/philips/hue_bulb_e27/
```

## Review Process

### 1. Identify Change Type

Classify the PR:

- New model profile
- Existing profile correction
- LUT update
- Metadata-only change
- Schema cleanup

### 2. Validate Directory Structure

Check that the layout follows repository conventions:

- `profile_library/<manufacturer>/<model>/model.json` exists
- Additional files are inside the model directory
- `library.json` was **not manually modified**

### 3. Establish the Canonical Model Identifier

Treat the generated or PR-reported model value as evidence, not automatically as the canonical identifier. Integrations can expose a marketing description, friendly name, bridge resource name, or protocol product ID instead of the manufacturer's stable model code.

For every new or renamed model directory:

1. Read [references/model_identifiers.md](references/model_identifiers.md), including the manufacturer-specific entry when one exists.
2. Cross-check the proposed directory against the manufacturer's technical product data, device label/manual, official device API, and Home Assistant device information or integration diagnostics as available.
3. Use the stable, specific manufacturer model code for the directory. Put other stable model values reported by integrations in `aliases` when they uniquely identify the same hardware.
4. Keep the full product or marketing name in `name`; add it to `aliases` only when it is actually reported as a model identifier and is needed for discovery.
5. Reject unstable identifiers such as entity/friendly names, room names, serial numbers, MAC addresses, bridge resource names such as `Light0x...`, and generic protocol identifiers shared by different products.
6. When renaming an existing profile directory, add the former canonical directory ID to `legacy_ids` so existing profile selections can migrate. Add that value to `aliases` as well only when it is also a real discovery identifier for the device.
7. Treat `manufacturer.json` aliases as discovery values too: remove exact duplicates, and require evidence that a proposed alias is exposed as the Home Assistant device manufacturer. A raw protocol signature or Zigbee manufacturer string is not sufficient unless the integration maps it to that Device Info field. For an existing uncertain alias, request exact Device Info evidence before removing it when removal could break discovery.

Do not infer a canonical ID from its shape alone. When authoritative sources conflict or uniqueness cannot be established, request contributor confirmation and state what evidence is missing.

### 4. Validate Metadata

Inspect `model.json` for required metadata.

Required checks:

- `name` present
- `device_type` present
- `calculation_strategy` present
- `measure_method` present
- `measure_device` present
- `created_at` present

Ensure:

- `created_at` is ISO formatted

### 5. Validate Strategy-Specific Data

Ensure the data matches the declared strategy.

#### Fixed

Expect:

- realistic fixed power value
- standby value when relevant

Potential issues:

- device clearly has multiple states
- unrealistic wattage

#### Linear

Expect:

- minimum and maximum calibration values
- plausible brightness mapping

Check for:

- inverted ranges
- impossible power curves

#### LUT

Expect:

- LUT file present
- sufficient datapoints

Check for:

- duplicate entries
- malformed rows
- large spikes or outliers
- redundant raw and compressed copies of the same LUT; compare decompressed content and retain one canonical copy, normally the repository's compressed form

#### Multi-switch / state-based

Expect:

- defined states
- internally consistent power values

### 6. Validate `only_self_usage`

`only_self_usage: true` means the device has a **built-in power meter**, so Powercalc only adds its self usage and names
the sensors `{} Device Power` / `{} Device Energy`.

- Allowed only on `smart_switch`, `smart_dimmer` and `power_meter`, and only for metering models (`HmIP-PSM` vs
  `HmIP-DRSI1`, Shelly `1PM` vs `1`, TP-Link `P110` vs `P100`). Hubs, bridges, repeaters and sensors never qualify;
  those describe their full draw with `fixed_config`.
- A metering plug or dimmer with only `standby_power`/`standby_power_on` and no flag most likely forgot it.
- Naming options (`power_sensor_naming`, `energy_sensor_naming`, `_friendly_` variants) are never allowed, in
  `sensor_config` or at the root. Contributors copy them instead of setting the flag; the flag produces that naming.

### 7. Validate Measurement Credibility

Look for signs the measurement may be unreliable:

- unrealistic standby values
- extremely rounded numbers
- missing measurement device
- copied data from similar models
- incomplete measurement explanation

Flag suspicious cases but avoid assuming bad intent.

### 8. Compare With Similar Profiles

Review neighbouring profiles in the library for consistency:

- naming conventions
- calculation strategy
- metadata completeness
- typical wattage ranges
- for `measure_device` the name matches one of the existing devices
- the manufacturer name is not repeated in the name

Large deviations should be questioned.

## Review Checklist

- [ ] Directory structure correct
- [ ] Directory uses the canonical, stable manufacturer model identifier
- [ ] Integration-specific stable identifiers are aliases; friendly, resource, serial, and generic identifiers are excluded
- [ ] Renamed profiles preserve former canonical directory IDs in `legacy_ids`
- [ ] Generated files not manually edited
- [ ] `manufacturer.json` present
- [ ] `model.json` schema appears valid`
- [ ] `created_at` valid ISO date
- [ ] Strategy matches provided data
- [ ] LUT data has no redundant raw/compressed duplicate
- [ ] Measurement metadata present
- [ ] Standby behaviour sensible
- [ ] `only_self_usage` matches a real built-in power meter, no sensor naming overrides
- [ ] Naming consistent with existing profiles

## Output Format

Responses should be concise and structured.

Structure:

1. **Verdict**
2. **Key Findings**
3. **Suggested Reviewer Comment**

### Verdict Values

- Approve
- Approve with nits
- Request changes

## Example Output

**Verdict:** Request changes

**Key findings:**

- `created_at` is not ISO formatted
- `calculation_strategy` is `lut`, but the LUT file is missing
- Standby value appears unusually high compared to similar devices

**Suggested reviewer comment:**

Thanks for contributing this profile! A few adjustments are needed before it can be merged:

2. Update `created_at` to ISO format
3. Add the LUT file referenced in the profile
4. Please double‑check the standby measurement as it appears higher than expected

Once these are addressed the profile should be ready for merge.

## Guardrails

The reviewer must:

- Avoid inventing measurement data
- Distinguish between **required fixes** and **suggestions**
- Assume contributors act in good faith
- Clearly state when manual verification is needed

## Optional Enhancements

The reviewer may additionally:

- Suggest exact wording for PR feedback
- Recommend improvements to measurement documentation
- Highlight missing metadata
- Identify inconsistencies with similar profiles

---

End of Skill Definition
