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

### 3. Validate Metadata

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

### 4. Validate Strategy-Specific Data

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

#### Multi-switch / state-based

Expect:

- defined states
- internally consistent power values

### 5. Validate Measurement Credibility

Look for signs the measurement may be unreliable:

- unrealistic standby values
- extremely rounded numbers
- missing measurement device
- copied data from similar models
- incomplete measurement explanation

Flag suspicious cases but avoid assuming bad intent.

### 6. Compare With Similar Profiles

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
- [ ] Generated files not manually edited
- [ ] `manufacturer.json` present
- [ ] `model.json` schema appears valid`
- [ ] `created_at` valid ISO date
- [ ] Strategy matches provided data
- [ ] Measurement metadata present
- [ ] Standby behaviour sensible
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
