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
3. Use the stable, specific manufacturer model code for the directory. Put other stable model values reported by integrations in `aliases` when they uniquely identify the same hardware, or when the manufacturer-specific guidance documents an intentional shared discovery alias that PowerCalc disambiguates by offering multiple profiles.
4. Use `name` for a concise, recognizable product name or device description; do not merely repeat the canonical model ID or model directory. When the official product name is identical to the model ID, use an official or clearly supported product category such as `Wireless Speaker` or `Smart Plug`. Add a product or marketing name to `aliases` only when it is actually reported as a model identifier and is needed for discovery.
5. Reject unstable identifiers such as entity/friendly names, room names, serial numbers, MAC addresses, bridge resource names such as `Light0x...`, and generic protocol identifiers shared by different products unless the manufacturer-specific guidance explicitly allows a shared integration-reported alias for discovery.
6. For every manufacturer, when renaming or consolidating an existing profile directory, normally add each former directory ID to `legacy_ids` so existing profile selections can migrate. Only values that were actually directory IDs belong there. Evaluate `aliases` independently: retain a former ID there only when it is also a real discovery identifier, because `legacy_ids` supports migration while `aliases` supports discovery. A deliberate manufacturer cleanup may instead use resolver-only compatibility when the old manufacturer and model are preserved as exact aliases and the complete pair is proven unique; document that exception in the manufacturer guidance.
7. Treat every model or manufacturer alias that has shipped in a generated `library.json` as a compatibility identifier. Never delete, rename, normalize, reformat, or replace it in place, even when it is redundant, malformed, deprecated, or no longer preferred. Add a corrected or canonical value alongside the released alias. `legacy_ids` is not a substitute: it migrates stored profile selections, while `aliases` participates in normal discovery and lookup. Before accepting a cleanup, compare the resulting lookup against the aliases in the relevant released library history.
8. Treat `manufacturer.json` aliases as discovery values too: remove exact duplicates, and require evidence that a proposed alias is exposed as the Home Assistant device manufacturer. A raw protocol signature or Zigbee manufacturer string is not sufficient unless the integration maps it to that Device Info field. For an existing uncertain alias, request exact Device Info evidence before removing it when removal could break discovery.

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
- integration restrictions use `compatible_integrations`; do not use the obsolete root-level `integration` key, which discovery ignores
- Store the manufacturer's claimed input or own-consumption wattage in `device_specs.rated_power` for any device type, not only lights. Keep it distinct from measured power values such as the library index's `max_power`. For a power supply or LED driver, an output rating is capacity rather than device consumption; for a switch, plug, UPS, or dimmer, a maximum connected or switchable load is likewise not `rated_power`. Leave the field unset when the manufacturer publishes only those capacity figures.
- Use root-level `mains_voltage` for the nominal AC supply voltage under which the profile was measured, not for the product's supported input-voltage range. Prefer an explicit PR statement or a recorded `voltage_range`; otherwise infer it only when the contributor's country agrees with the measured regional product or plug/fitting variant and measurement equipment. Reuse and extend `utils/library/contributor_countries.json` for verified contributor-country evidence. A fitting such as E27 alone is insufficient because it spans multiple mains regions. Leave ambiguous cross-region profiles unset, and do not assign `mains_voltage` when a low-voltage DC/AC source was measured downstream of the mains adapter or transformer.
- Put the protocols the device itself uses for supported operation in `device_specs.connectivity`. Record Matter together with its verified transport, for example `["matter", "thread"]` or `["wifi", "matter"]`; Matter alone does not identify the radio. For gateways, include both sides that the hardware actually communicates over, such as Zigbee and Ethernet. Do not infer connectivity from the manufacturer, an integration name, a cloud API, or the phone-side setup flow. In particular, Bluetooth required only on the phone for commissioning is not device Bluetooth functionality. Check product generations separately when a manufacturer moved from Zigbee to Matter-over-Thread or otherwise changed protocol.
- Put verified retail packaging barcodes (EAN-8, UPC-12, EAN-13, or GTIN-14) in the `ean` array. Include the verified barcodes of single-device and multipack packaging when every pack contains the exact same device model, because each barcode can help users find the profile. Exclude bundles, fittings, revisions, or packs containing a different electrical model. Do not infer that a numeric model, article, SKU, or 12NC is a barcode merely because its length or check digit is valid. Keep a barcode in `aliases` as well when an integration reports it as a model identifier and removing it would break discovery; `ean` is product metadata, not a replacement for discovery aliases.
- Set `product_url` only to a stable HTTPS page from the manufacturer or brand owner that identifies the exact model or measured variant. Prefer the canonical URL declared by the page or the stable destination after redirects, and remove tracking, chooser, search, and variant-selection parameters when the clean URL still identifies the same product. Prefer an English or language-neutral page and use one regional storefront consistently within a manufacturer where the exact products exist; retain another region when the model or electrical variant is region-specific or unavailable on the preferred storefront.
- Prefer an exact product page over a family, identification, knowledgebase, or technical page. A family page is acceptable only when it explicitly contains the measured variant, and a model-specific archived, support, knowledgebase, or technical HTML page is acceptable when no product page survives. Do not use PDF manuals, declarations, datasheets, or catalogs as `product_url`; those may be research evidence but are not product pages. Do not replace a precise legacy source with a URL that redirects to a category page.
- Do not use search results, category pages, generic product resolvers, or third-party retailer listings; a retailer's page is acceptable only when that retailer owns the product brand. In particular, reject lookup URLs that identify the product only through a query parameter such as `?sku=...`, even when the resolved page happens to show the correct model. Do not link a current successor or revised product page when its electrical specifications differ from the measured profile.

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

Normally expect:

- minimum and maximum calibration values
- plausible brightness mapping

A non-metering `smart_dimmer` may intentionally omit `linear_config`: its profile supplies only
`standby_power` and `standby_power_on`, while the user provides the connected load's minimum and maximum power during
setup. Do not flag that pattern as incomplete when the self-usage measurements are credible.

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

When several identical lights are measured through one Home Assistant group, inspect the measurement-tool version and the recorded light count before treating the LUT as aggregate power. The light runner divides every reading, including standby, by the configured number of lights; an explicitly configured multi-light run therefore produces a per-light profile.

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

### 9. Preserve Manufacturer Learnings

During an ongoing manufacturer-by-manufacturer consistency audit, automatically record new, reusable, evidence-backed identifier, discovery, naming, or measurement rules in `references/model_identifiers.md` after completing each manufacturer. Keep additions concise and manufacturer-specific; do not add a section when the review produced no non-obvious reusable guidance.

### 10. Track Unresolved Research

During a profile-library consistency audit, read and maintain [references/profile_review_todo.md](references/profile_review_todo.md). Add a checkbox only for a concrete unresolved identity, revision, discovery, barcode, or measurement question with a clear next evidence requirement; do not use it as a duplicate list of every missing metadata field. Mark an item complete when it is resolved and record the deciding evidence and commit or PR when available.

## Review Checklist

- [ ] Directory structure correct
- [ ] Directory uses the canonical, stable manufacturer model identifier
- [ ] `name` is meaningful and does not merely repeat the canonical model ID or directory
- [ ] Integration-specific discovery identifiers are aliases; friendly, resource, serial, and undocumented generic identifiers are excluded
- [ ] No alias from a previously generated library is removed or changed; corrected values are added alongside it
- [ ] Verified single-device and exact-model multipack barcodes use `ean`; discovery aliases are retained independently
- [ ] Product URL is canonical, parameter-clean where possible, and identifies the exact measured product or variant
- [ ] Generated files not manually edited
- [ ] `manufacturer.json` present
- [ ] `model.json` schema appears valid`
- [ ] `created_at` valid ISO date
- [ ] Integration restrictions use `compatible_integrations`
- [ ] Strategy matches provided data
- [ ] LUT data has no redundant raw/compressed duplicate
- [ ] Measurement metadata present
- [ ] Standby behaviour sensible
- [ ] `only_self_usage` matches a real built-in power meter, no sensor naming overrides
- [ ] Naming consistent with existing profiles
- [ ] Concrete unresolved questions recorded in the profile review TODO

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
