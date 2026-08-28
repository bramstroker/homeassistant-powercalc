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
- a generic white-label or protocol identifier shared by materially different products, unless the manufacturer-specific guidance explicitly documents it as an integration-reported discovery alias that PowerCalc safely presents as multiple candidates;
- a numeric Matter product ID unless there is evidence that it uniquely identifies the physical model.

If no unique identifier can be established, request manual verification. If the device exposes only a generic identifier, it may be suitable only as a custom profile.

## Manufacturer guidance

| Manufacturer | Common canonical identifiers in this library | Where to confirm | Common alias or rejection cases |
|---|---|---|---|
| 3A Smart Home / Nue | Prefer a product-specific code printed on the complete device; retain an exact `LXN...` or `LXT...` Zigbee value when no more specific verified code is available | Product or packaging label and manufacturer technical data; then HA Device Info and the raw Zigbee signature | `LXN...` and `LXT...` values can identify the embedded controller and may be shared by different complete products. Follow the detailed 3A Smart Home guidance below. |
| Amazon | Printed hardware model codes such as `B7W64E`, `C2H4R9`, and `L9D29R` | Product label, regulatory filings and official device documentation; then HA Device Info and Alexa integration diagnostics | ASINs are retail catalog identifiers, while Alexa device types and family-prefixed values are discovery aliases. Existing or confirmed Amazon serial/DSN discovery aliases are an intentional exception. Follow the detailed Amazon guidance below. |
| IKEA | Product codes such as `E2499`, `E2206`, `LED2405G8`, `L2206`, `T1828`, and driver codes such as `ICPSHC24-30EU-IL-1` | IKEA product page technical information under **Model identifier**, rating label/manual, then HA/ZHA or Zigbee diagnostics | Hue may report a descriptive value such as `VARMBLIXT colour and white`; keep that as an alias when needed. Reject Hue resource names such as `Light0x...`. Matter numeric IDs are often not unique. |
| Signify / Philips Hue | Zigbee model codes such as `LCA...`, `LCT...`, `LWA...`, `LTW...`, and stable luminaire/product codes such as `92900...` when that is the device model | Hue API v2 device `product_data.model_id`, HA Hue Device information, product label | Do not confuse a retail EAN, user-assigned Hue name, or bridge resource name with the device model. Regional codes can be aliases only when they are stable identifiers for the same hardware. |
| Shelly | Hardware codes such as `SHPLG-S`, `SNSW-...`, `S3SW-...`, `S4SW-...`, and `SPEM-...` | Gen2+ `Shelly.GetDeviceInfo` response field `model`; Gen1 `/shelly` device info; product label and official documentation | Names such as `Shelly Plus Plug S` are useful display names but are not preferable to the hardware code. Never use the device ID containing its MAC suffix. |
| TP-Link Kasa / Tapo | Product models such as `HS110`, `KP115`, `P110`, `P110M`, `L530` | Product label or body, Kasa/Tapo Device Info, HA Device information, official support page | Exclude nicknames and serial numbers. Record a hardware revision only when it is reported as part of the discovery identifier or measurements establish materially different power behavior. |
| Aqara / Xiaomi | Stable Zigbee identifiers such as `lumi.plug.maeu01` or printed product codes such as `ZNLDP12LM`, depending on what identifies the hardware | Product label/manual and HA ZHA/Zigbee device signature; cross-check the other stable code and add it as an alias when appropriate | Marketing names such as `Aqara Smart Plug` are not enough on their own. Confirm that a `lumi.*` identifier is specific to one hardware model. |
| LEDVANCE / OSRAM | Prefer the exact official manufacturer article/model code, such as an `AC...` code or an older OSRAM article number. Retain a device-reported Zigbee model such as `CLA60 RGBW Z3` as canonical only when no more specific official article code can be established for the measured hardware. | Official LEDVANCE product datasheet, declaration or catalog; product label; then HA/integration diagnostics and Zigbee signature | Exact protocol model strings, integration-specific IDs, and officially mapped GTINs can be aliases. Follow the detailed LEDVANCE guidance below. |
| Innr | Printed and device-reported codes such as `RB 285 C`, `RS 230 C`, `SP 240` | Official Innr product page or declaration, product label/manual, then HA ZHA/Zigbee device signature | Keep spaces and suffix letters when they are part of the model code. Bundle SKUs and regional sibling models are not aliases by default. Follow the detailed Innr guidance below. |
| Lidl | Printed product/type codes such as `HG06462A`, `HG08131B`, a specific article code, or an IAN-based identifier when that is the only stable label code | Product or packaging label/manual, official Lidl documentation, then current HA Device Info and the integration's raw Zigbee signature | Reject generic Zigbee models such as `TS0502A` and `TS0505B`. Do not assume a raw `_TZ...` string is a manufacturer alias. Follow the detailed Lidl guidance below. |
| WiZ | Prefer the exact WiZ/Signify material or article number (12NC), commonly beginning with `929...`; retain another verified printed manufacturer model when no 12NC can be established | Official WiZ product specifications, product or packaging label, then HA WiZ Device information and the raw `moduleName` | `SHRGB`, `SHRGBC`, `SHTW`, and related `SH...` values are module/configuration codes rather than unique article numbers. Keep confirmed values as intentionally shared discovery aliases. Follow the detailed WiZ guidance below. |
| Sonos | Prefer the exact manufacturer article/model number printed on the product or packaging when it uniquely identifies the measured hardware. Preserve established product-name directories unless a verified canonical migration is intentionally requested. | Product label/packaging and official Sonos documentation; then HA Sonos Device information, where `model_id` comes from the speaker's `modelNumber` | `S...` values are useful discovery aliases when one-to-one with the measured generation, but are not automatically retail article numbers. Product names and S-codes can both be generation-ambiguous. Follow the detailed Sonos guidance below. |
| Sonoff | Printed product codes such as `ZBMINI`, `ZBMINIR2`, and `B02BA60` | Product label/manual, eWeLink or HA Device information, Zigbee device signature | Do not substitute an underlying generic Tuya/Zigbee identifier for a branded Sonoff code. |
| Tuya and white-label devices | No safe universal pattern | Require a branded model from the product label/manufacturer and compare its full Zigbee signature with known devices | Identifiers such as `TS0601`, `TS0505B`, and `_TZE...` values can cover different hardware. Do not add them as a directory or alias unless uniqueness for the measured device is demonstrated. |

## Amazon

Apply these rules when reviewing or normalizing Amazon Echo and Alexa profiles:

1. Prefer the exact physical hardware model printed on the device or established by official or regulatory documentation as the canonical directory ID. Do not use an Amazon Standard Identification Number (ASIN), commonly a ten-character retail code beginning with `B0`, as the canonical model merely because it appears on a product page or order. When replacing an existing ASIN directory with the verified hardware code, add the former directory ID to `legacy_ids`; add it to `aliases` only when an integration is also confirmed to report it.
2. Preserve exact Alexa device types such as `A2U21SRK4QGSE1` and `A18O6U1UQFJ0XK` as discovery aliases when they map to the measured hardware. Alexa Media Player may expose a fallback model composed as `<deviceFamily> <deviceType>`, producing values such as `ECHO ...` and `KNIGHT ...`; retain the exact prefixed value when Device Info, diagnostics, integration source, or the original PR confirms it.
3. Amazon serial numbers or device serial numbers (DSNs) are an intentional exception to the universal alias exclusion when the exact value already exists as an Amazon profile alias or is confirmed as a model value required for Home Assistant discovery. Keep it only on the profile for the device from which it was captured, never use it as the canonical directory ID, and never copy or generalize it to sibling profiles. A stable Alexa device type should be added alongside it when available, rather than replacing an established discovery alias.
4. Check every alias against the canonical IDs and aliases of other Amazon profiles. Similar Echo models can have distinct physical codes, such as clock and non-clock variants, and an alias must not point to a sibling profile merely because they share a generation or enclosure.
5. Preserve a verified regional or hardware model variant when the contributor confirms the exact printed label. If an existing code differs by one character from independently documented codes, do not silently normalize it; ask for a label photo or exact transcription and use `legacy_ids` if a confirmed typo later requires a directory migration.
6. Alexa speakers may reject the measurement tool's directly streamed test MP3 and play a spoken error instead. Confirm that pink noise or another continuous, documented test signal was actually playing while volume levels were measured. For older profiles created before the tool could disable direct streaming, ask whether playback was started manually, for example through Spotify, when the curve or PR evidence is inconclusive.
7. Use concise product names with consistent generation formatting, such as `Echo Dot (Gen3)` and `Echo Show 8 (Gen2)`. Distinguish variants such as `with clock` only when they represent different physical models and profiles.

When an Amazon hardware code, ASIN, Alexa device type, family-prefixed model, or serial discovery value cannot be reconciled, keep the established profile available and ask for the product-label code, exact Home Assistant Device Info fields, originating integration, and measurement playback method.

## 3A Smart Home / Nue

Apply these rules when reviewing or normalizing 3A Smart Home and Nue profiles:

1. Treat device-reported codes such as `LXN60-LS27-Z30` and `LXT56-LS27LX1.7` as Zigbee hardware evidence, not automatic proof of the complete product's canonical article code. In particular, an `LXT...` controller identifier can be exposed by both a complete downlight and a standalone RGBW strip controller.
2. Prefer the exact product-specific code printed on the complete light, dimmer, or packaging when it can be verified. An apparent OEM family code such as `WL-SD001-9W` or `WL-SD001-12W` is only a lead until the contributor confirms it on the measured product; verify wattage and, for downlights, lumen output and cut-out size before mapping it.
3. If a verified product code replaces an existing `LXN...` or `LXT...` directory, add the former directory ID to `legacy_ids` for existing installations and retain it in `aliases` when Home Assistant or the originating integration actually reports it. A confirmed shared controller alias may occur on multiple profiles so PowerCalc can offer the matching candidates; never use that shared alias alone to merge measurements or claim hardware equivalence.
4. Preserve complete suffixes and revisions such as `.1` and `.3`. Do not assume sibling controller codes identify equivalent dimmers or share self-usage merely because the base code and product description match.
5. Accept `3A Smart Home DE` and other manufacturer aliases only when the exact value appears in Home Assistant Device Info for the originating integration. Do not generate capitalization variants solely for completeness or infer aliases from a raw signature without confirming how Home Assistant exposes it.
6. Use the branded product line, such as `Nue`, and the verified product type in `name`; omit the generic word `Smart`, the protocol name `ZigBee`, and the manufacturer name when they add no product distinction. Format ratings with a space, for example `Nue RGBW Downlight (9 W)`.

When a controller identifier and apparent product code cannot be reconciled, keep the established profile unchanged and ask for a product-label or packaging photo plus the exact Home Assistant manufacturer, model, originating integration, wattage, and relevant physical specifications.

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

## Innr

Apply these rules when reviewing or normalizing Innr profiles:

1. Use the exact Innr type code as the canonical directory ID, including spaces and capability suffixes: for example, `RB 285 C`, `RS 230 C`, and `SP 240`. Do not collapse the spaces, remove suffix letters such as `C` or `T`, or replace the code with a marketing-family name.
2. Confirm the code through the type-number section of an official Innr product page, a declaration of conformity, or the product label/manual. Use Home Assistant device information and the raw Zigbee signature to establish what integrations actually report. Treat Zigbee2MQTT mappings as corroboration rather than proof that grouped devices have identical power behavior.
3. Add a stable integration-reported model string to `aliases` only when it uniquely maps to the same hardware. A verified value such as `On/Off plug (SP 220)` is a valid alias; do not generate aliases merely by removing spaces or punctuation from the canonical code.
4. Do not add retail bundle suffixes such as `-2` or `-4`, EANs, or package SKUs as aliases unless an integration demonstrably reports them as the device model. Likewise, do not alias regional siblings such as `SP 240`, `SP 242`, and `SP 244` without evidence that socket type, voltage range, electronics, and measured self-usage are equivalent.
5. Keep distinct type codes separate when they merely share a marketing name or appear in one Zigbee catalog entry. For example, sibling codes such as `RB 247 T`, `RB 248 T`, and `RB 249 T` are not interchangeable without official hardware equivalence and compatible measurements.
6. Put the official product description in `name`, omit the manufacturer and protocol name (`Innr`, `Zigbee`), and match the verified fitting and capabilities. Prefer concise Innr family wording such as `Smart Bulb Colour E27`, `Smart Plug`, `Strip Light Colour`, `Outdoor Smart Plug`, and `Round Ceiling Light`. Do not claim tunable-white or colour support when the profile strategy and device capabilities do not support it.
7. Cross-check `only_self_usage` per exact plug model. Current verified mappings are metering for `SP 120` and `SP 240`, and non-metering for `SP 220`, `SP 224`, and `OSP 210`. Reverify when a hardware revision or regional model differs; do not transfer the flag based only on the shared `SP` or plug family name.

When an Innr code, integration-reported value, or regional variant cannot be reconciled, ask for the product-label type code, the exact Home Assistant model value and originating integration, and confirmation of fitting, region, and built-in power metering before adding aliases or sharing measurements.

## Lidl

Apply these rules when reviewing or normalizing Lidl profiles, including Livarno and Silvercrest products:

1. Prefer the exact code printed on the product or packaging as the canonical directory ID. Lidl lighting commonly uses an `HG...` type code with a meaningful variant suffix; some products instead have a stable article code or an IAN-based identifier. Preserve punctuation and suffix letters that distinguish the measured hardware.
2. Reject generic Tuya/Zigbee model values such as `TS0502A` and `TS0505B` as directory IDs and aliases unless one-to-one uniqueness for the measured hardware is demonstrated. If the integration exposes only such a shared value, keep the profile manual-only rather than enabling unsafe automatic discovery.
3. When the directory code conflicts with the model recorded in an older PR, Zigbee catalog, or Home Assistant Device Info, do not infer equivalence from matching capabilities or an A/B/C suffix. Ask for the printed product code and the current exact Home Assistant `manufacturer`, `model`, and `model_id`, including the originating integration and values after any linked converter fix.
4. Add a conflicting integration-reported code to `aliases` only after confirming that it uniquely identifies the same physical variant. Do not add it to `legacy_ids` unless it was actually a former canonical directory ID in the library; a stale PR value, converter bug, or catalog mapping alone is not a legacy ID.
5. Treat raw Zigbee manufacturer strings such as `_TZ...` as signature evidence, not automatically as `manufacturer.json` aliases. Confirm that ZHA, Zigbee2MQTT, or another integration exposes the exact value as the Home Assistant device manufacturer. Remove exact duplicate aliases, but request current Device Info evidence before deleting a distinct historical alias that may still support discovery.
6. Keep hardware variants separate when their printed codes differ unless official documentation and measurements establish electrical equivalence. Codes ending in `A`, `B`, or `C` may represent distinct fittings, shapes, electronics, or capabilities even when a Zigbee catalog groups them.
7. Use the verified product description in `name`. Lidl's product brands such as `Livarno Home`, `Livarno Lux`, and `Silvercrest` may remain because they identify the branded product even though the library manufacturer is Lidl. Normalize capitalization and capability terms, but do not invent details absent from the label, official documentation, or device capabilities.

When a Lidl label code and integration-reported value cannot be reconciled, ask for a product or packaging label photo and the current Home Assistant Device Info fields. Keep the profile discoverable only through identifiers proven specific to the measured variant.

## WiZ

Apply these rules when reviewing or normalizing WiZ and WiZ-powered Philips Smart LED profiles:

1. Prefer the exact WiZ/Signify material or article number (12NC) as the canonical directory ID, commonly a `929...` value. Confirm it on an official WiZ product page, product or packaging label, or equivalent manufacturer documentation. Do not substitute the retail EAN/GTIN for the 12NC or describe an EAN as the model number. Retain another concrete printed manufacturer model, such as a regional alphanumeric code, when no more authoritative 12NC can be established.
2. Home Assistant's WiZ integration derives its displayed `model` from the device `moduleName`. Values such as `SHRGB`, `SHRGBC`, `SHRGB1C`, `SHTW`, and `SHDW1` describe a controller/module configuration and can be shared by products with different fittings, wattages, shapes, or electronics. Do not use such a value as the canonical directory ID when a specific article number is known.
3. Add the exact `SH...` value reported for each measured device to `aliases`, even when another WiZ profile uses the same alias. This is an intentional WiZ exception: without that alias the article-number profile cannot be discovered, and PowerCalc can present all matching profiles for the user to choose from. Require evidence from Home Assistant Device information, diagnostics, the original profile PR, or the raw `moduleName`; do not infer an alias merely from advertised color capabilities.
4. When replacing an existing `SH...` directory with its verified article number, put the former directory ID in both `legacy_ids` and `aliases`: `legacy_ids` preserves existing selections, while `aliases` preserves discovery. A former non-reported internal slug belongs only in `legacy_ids`.
5. Never merge profiles merely because they share an `SH...` alias. Establish that they are the same physical product using the exact 12NC, label, official specifications, and where useful an exact EAN mapping. Shared module codes alone are evidence of discovery ambiguity, not hardware equivalence.
6. For confirmed duplicate physical products, consolidate under the verified article number and retain the most credible calibration data. Compare supported modes, LUT completeness, measurement setup, standby power, and peak draw against the rated power. A complete color-temperature and HS measurement reaching a plausible rated draw is normally preferable to an incomplete LUT with an implausibly low maximum; preserve relevant authorship and measurement provenance when consolidating.
7. If the exact article number or duplicate relationship remains uncertain, ask for the product or packaging label, exact Home Assistant Device information, originating integration, and full `moduleName`. Keep the established profile available until the evidence supports a migration; do not invent a regional 12NC suffix from a similar product page.
8. Spell the manufacturer `WiZ`. Use the official product description in `name`, distinguish WiZ-branded and Philips Smart LED products where that branding identifies the product line, and keep EANs and module codes out of the display name unless they materially clarify unresolved source evidence.

## Sonos

Apply these rules when reviewing or normalizing Sonos profiles:

1. Distinguish three identifiers: the existing Powercalc directory ID, the manufacturer article/model number printed on the device or packaging, and the Sonos `modelNumber` commonly formatted as `S...`. Home Assistant's Sonos integration exposes the speaker `modelNumber` as `model_id` and the product name, with the `Sonos ` prefix removed, as `model`. Do not treat the S-code as the printed article number without separate manufacturer evidence.
2. For an existing profile, preserve its directory ID unless the review explicitly establishes and requests a canonical migration. Adding a newly verified S-code to `aliases` does not require `legacy_ids`; use `legacy_ids` only when the directory itself is renamed, and include the former directory ID there so existing selections can migrate.
3. Add an exact S-code to `aliases` only when device information, diagnostics, the original profile PR, or equivalent device evidence maps it one-to-one to the measured hardware generation. Do not infer the code from the marketing name or reuse a code across generations merely because Sonos presents them as one product family.
4. Treat generation-sensitive products as ambiguous until confirmed. This commonly affects One, One SL, Beam, Play:5, Sub, and IKEA SYMFONISK products. Ask for the exact Home Assistant `model` and `model_id`, the originating integration, the printed article/model number, and the hardware generation before adding an alias or sharing calibration data.
5. Keep distinct Sonos generations or product lines separate even when their names are similar. In particular, `Play:5` and `Five` are different products: never use `Five` as an alias for a Play:5 profile when a separate Five profile exists. Check every proposed name alias case-insensitively against both directory IDs and aliases to avoid discovery collisions.
6. A generic value such as `Sub` is insufficient evidence for a generation-specific profile. A bonded Sub may not expose standalone Home Assistant Device information, so request the physical label or packaging code and the generation rather than guessing from the household or parent speaker.
7. Use official product capitalization in `name`, omit the manufacturer, and format generation labels consistently, for example `Sub (Gen 1)`, `SYMFONISK Floor Lamp`, and `SYMFONISK Table Lamp`. Add a product name to `aliases` only when an integration actually reports it as a discovery identifier and it cannot collide with another profile.

When the printed article number, S-code, product name, or generation cannot be reconciled, keep the established profile unchanged and request contributor evidence. Do not add every historically associated S-code to a generic profile as a fallback.

## Useful primary references

- [Powercalc library structure](../../../../docs/source/library/structure.md) explains that the directory is the model ID and aliases are alternate discovery identifiers.
- [Powercalc measurement output guidance](../../../../docs/source/contributing/measure/output.md) requires the exact model identifier rather than the marketing name.
- [Powercalc Matter limitations](../../../../docs/source/library/matter-limitations.md) explains why Matter product IDs can be unsafe for automatic discovery.
- [IKEA's E2499 product page](https://www.ikea.com/de/en/p/varmblixt-led-table-wall-lamp-dimmable-smart-white-glass-colour-and-white-spectrum-70612940/) is an example of the **Model identifier** field in IKEA technical product information.
- [Shelly device information API](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Shelly/) documents `Shelly.GetDeviceInfo.model`.
- [TP-Link model-number guidance](https://www.tp-link.com/ae/support/faq/2053/) shows where the product model is printed and exposed in its apps.
- [Innr product pages](https://innr.com/collections/frontpage) list official product names and type numbers.
- [Innr declarations of conformity](https://innr.com/pages/declarations-of-conformity) corroborate exact type codes and regional variants.
- [Home Assistant's Sonos entity implementation](https://github.com/home-assistant/core/blob/dev/homeassistant/components/sonos/entity.py) maps the speaker product name to `model` and `modelNumber` to `model_id`.
- [Home Assistant's WiZ entity implementation](https://github.com/home-assistant/core/blob/dev/homeassistant/components/wiz/entity.py) derives the displayed model from the WiZ `moduleName`.
- [pywizlight's bulb library](https://github.com/sbidy/pywizlight/blob/master/pywizlight/bulblibrary.py) documents the structure and capability meaning of WiZ module names.
- [WiZ product specifications](https://www.wizconnected.com/en-nz/p/downlight-35-inch-recessed-downlight-8w/8720169072251) show the material number (12NC) separately from the EAN.

## Review evidence

In a finding, state all three values when relevant:

- canonical directory model ID;
- alternate integration-reported value to preserve in `aliases`;
- unstable or user-specific suffix to remove.

Example: use `E2499` as the directory, preserve `VARMBLIXT colour and white` as the Hue-reported alias, and remove the bridge resource suffix `Light0x07C2` from the display name.
