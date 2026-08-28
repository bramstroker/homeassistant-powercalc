# Canonical Model Identifier Reference

Use this reference when a PR adds or renames a power-profile model directory. Its patterns are review clues, not validation regexes: manufacturers introduce new families, and an identifier's shape alone never proves that it is canonical or unique.

## Decision rule

The directory name is the stable, specific manufacturer model code for the measured hardware. Discovery values that other integrations report for the same hardware belong in `aliases`.

Prefer evidence in this order:

1. Manufacturer technical data, rating label, manual, support page, or official device API.
2. Home Assistant Device information and integration diagnostics. Check both `model` and `model_id`; record which integration supplied the value.
3. An established protocol catalog such as Zigbee2MQTT only as corroboration, especially when it maps a device signature to a manufacturer code.
4. Retail listings, forum posts, and search snippets only as leads to verify elsewhere.

The PR generator cannot determine which reported value is canonical in every integration. A value shown as “Model ID” in a generated PR may still be an integration description or bridge-generated resource name.

## Universal exclusions

Do not use these as a directory name or alias:

- Home Assistant entity names, user-assigned device names, or room names;
- serial numbers, MAC addresses, network addresses, and bridge resource names such as `Light0x...`;
- a marketing family name that covers multiple hardware variants;
- a generic white-label or protocol identifier shared by materially different products;
- a numeric Matter product ID unless there is evidence that it uniquely identifies the physical model.

If no unique identifier can be established, request manual verification. If the device exposes only a generic identifier, it may be suitable only as a custom profile.

## Manufacturer guidance

| Manufacturer | Common canonical identifiers in this library | Where to confirm | Common alias or rejection cases |
|---|---|---|---|
| IKEA | Product codes such as `E2499`, `E2206`, `LED2405G8`, `L2206`, `T1828`, and driver codes such as `ICPSHC24-30EU-IL-1` | IKEA product page technical information under **Model identifier**, rating label/manual, then HA/ZHA or Zigbee diagnostics | Hue may report a descriptive value such as `VARMBLIXT colour and white`; keep that as an alias when needed. Reject Hue resource names such as `Light0x...`. Matter numeric IDs are often not unique. |
| Signify / Philips Hue | Zigbee model codes such as `LCA...`, `LCT...`, `LWA...`, `LTW...`, and stable luminaire/product codes such as `92900...` when that is the device model | Hue API v2 device `product_data.model_id`, HA Hue Device information, product label | Do not confuse a retail EAN, user-assigned Hue name, or bridge resource name with the device model. Regional codes can be aliases only when they are stable identifiers for the same hardware. |
| Shelly | Hardware codes such as `SHPLG-S`, `SNSW-...`, `S3SW-...`, `S4SW-...`, and `SPEM-...` | Gen2+ `Shelly.GetDeviceInfo` response field `model`; Gen1 `/shelly` device info; product label and official documentation | Names such as `Shelly Plus Plug S` are useful display names but are not preferable to the hardware code. Never use the device ID containing its MAC suffix. |
| TP-Link Kasa / Tapo | Product models such as `HS110`, `KP115`, `P110`, `P110M`, `L530` | Product label or body, Kasa/Tapo Device Info, HA Device information, official support page | Exclude nicknames and serial numbers. Record a hardware revision only when it is reported as part of the discovery identifier or measurements establish materially different power behavior. |
| Aqara / Xiaomi | Stable Zigbee identifiers such as `lumi.plug.maeu01` or printed product codes such as `ZNLDP12LM`, depending on what identifies the hardware | Product label/manual and HA ZHA/Zigbee device signature; cross-check the other stable code and add it as an alias when appropriate | Marketing names such as `Aqara Smart Plug` are not enough on their own. Confirm that a `lumi.*` identifier is specific to one hardware model. |
| LEDVANCE / OSRAM | Prefer the exact official manufacturer article/model code, such as an `AC...` code or an older OSRAM article number. Retain a device-reported Zigbee model such as `CLA60 RGBW Z3` as canonical only when no more specific official article code can be established for the measured hardware. | Official LEDVANCE product datasheet, declaration or catalog; product label; then HA/integration diagnostics and Zigbee signature | Exact protocol model strings, integration-specific IDs, and officially mapped GTINs can be aliases. Follow the detailed LEDVANCE guidance below. |
| Innr | Printed and device-reported codes such as `RB 285 C`, `RS 230 C`, `SP 240` | Product label/manual and HA ZHA/Zigbee device signature | Keep spaces and suffix letters when they are part of the model code; do not reduce the directory to the marketing family. |
| Sonoff | Printed product codes such as `ZBMINI`, `ZBMINIR2`, and `B02BA60` | Product label/manual, eWeLink or HA Device information, Zigbee device signature | Do not substitute an underlying generic Tuya/Zigbee identifier for a branded Sonoff code. |
| Tuya and white-label devices | No safe universal pattern | Require a branded model from the product label/manufacturer and compare its full Zigbee signature with known devices | Identifiers such as `TS0601`, `TS0505B`, and `_TZE...` values can cover different hardware. Do not add them as a directory or alias unless uniqueness for the measured device is demonstrated. |

## LEDVANCE / OSRAM

Apply these rules when reviewing or normalizing LEDVANCE and OSRAM profiles:

1. Prefer the exact official manufacturer article/model code as the directory ID. LEDVANCE codes such as `AC26447` take precedence over a GTIN, marketing name, integration-specific value, or malformed concatenation when official product data establishes the mapping. Older OSRAM article numbers and device-reported Zigbee model strings remain valid canonical IDs when they are the most specific verified manufacturer identifier available.
2. Confirm the mapping with an official LEDVANCE product page, datasheet, declaration of conformity, catalog, or product label. Use Home Assistant diagnostics, the integration's raw device information, LEDVANCE firmware data, or an established Zigbee catalog to determine which identifiers are actually reported for discovery.
3. Add exact alternative identifiers for the same hardware to `aliases`. These may include another integration's stable model string, an official Zigbee model string, or a GTIN/EAN that official data maps one-to-one to the article. Do not add a transcribed typo or an unverified numeric string as an alias.
4. When an existing directory is renamed, add its old directory ID to `legacy_ids`. If the old value was malformed or was only an internal directory slug, keep it out of `aliases` unless an integration is confirmed to report it. A value may appear in both lists when it is both a former canonical ID and a genuine discovery identifier.
5. Do not create separate profiles solely for a housing color or finish when official specifications show the variants are otherwise the same device and the measurements apply to both. Prefer the measured article code when known; otherwise choose one documented article code as canonical and add the other cosmetic article codes and their exact GTINs as aliases. Keep color out of `name` when the profile intentionally covers every finish.
6. Do not combine variants that differ in wattage, fitting, dimensions, light capabilities, electronics, or measured behavior. A shared marketing family or Zigbee model string alone is insufficient evidence that these variants can share measurements.
7. Keep display names consistent with the established LEDVANCE spelling: `SMART+` and `LIGHTIFY` for product families, and `WiFi`, `ZB`, `RGBW`, `RGB + TW`, `TW`, and `DIM` where those terms describe the verified product. Put the complete product description in `name`, omit the manufacturer name itself, and do not include a color/finish that is intentionally represented by aliases.

When the official code and the measured variant still cannot be reconciled, ask the contributor for a product-label or packaging photo, the exact identifier from Home Assistant or the originating integration, and confirmation of relevant capabilities such as RGB versus tunable white. Do not block on a cosmetic finish alone when the variants are demonstrably electrically identical.

## Useful primary references

- [Powercalc library structure](../../../../docs/source/library/structure.md) explains that the directory is the model ID and aliases are alternate discovery identifiers.
- [Powercalc measurement output guidance](../../../../docs/source/contributing/measure/output.md) requires the exact model identifier rather than the marketing name.
- [Powercalc Matter limitations](../../../../docs/source/library/matter-limitations.md) explains why Matter product IDs can be unsafe for automatic discovery.
- [IKEA's E2499 product page](https://www.ikea.com/de/en/p/varmblixt-led-table-wall-lamp-dimmable-smart-white-glass-colour-and-white-spectrum-70612940/) is an example of the **Model identifier** field in IKEA technical product information.
- [Shelly device information API](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Shelly/) documents `Shelly.GetDeviceInfo.model`.
- [TP-Link model-number guidance](https://www.tp-link.com/ae/support/faq/2053/) shows where the product model is printed and exposed in its apps.

## Review evidence

In a finding, state all three values when relevant:

- canonical directory model ID;
- alternate integration-reported value to preserve in `aliases`;
- unstable or user-specific suffix to remove.

Example: use `E2499` as the directory, preserve `VARMBLIXT colour and white` as the Hue-reported alias, and remove the bridge resource suffix `Light0x07C2` from the display name.
