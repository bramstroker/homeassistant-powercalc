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
| Apple | Printed Apple hardware model numbers such as `A2374` and `A2825` | Apple regulatory product tables and information guides; then HA Apple TV Device Info and pyatv model mappings | Regional or color-specific `M...` order/SKU codes are not the canonical hardware model. Preserve exact pyatv names as discovery aliases. Follow the detailed Apple guidance below. |
| IKEA | Product codes such as `E2499`, `E2206`, `LED2405G8`, `L2206`, `T1828`, and driver codes such as `ICPSHC24-30EU-IL-1` | IKEA product page technical information under **Model identifier**, rating label/manual, then HA/ZHA or Zigbee diagnostics | Hue may report a descriptive value such as `VARMBLIXT colour and white`; keep that as an alias when needed. Reject Hue resource names such as `Light0x...`. Matter numeric IDs are often not unique. |
| Signify / Philips Hue | Zigbee model codes such as `LCA...`, `LCT...`, `LWA...`, `LTW...`, and stable luminaire/product codes such as `92900...` when that is the device model | Hue API v2 device `product_data.model_id`, HA Hue Device information, product label | Do not confuse a retail EAN, user-assigned Hue name, or bridge resource name with the device model. Regional codes can be aliases only when they are stable identifiers for the same hardware. |
| Shelly | Hardware codes such as `SHPLG-S`, `SNSW-...`, `S3SW-...`, `S4SW-...`, and `SPEM-...` | Gen2+ `Shelly.GetDeviceInfo` response field `model`; Gen1 `/shelly` device info; product label and official documentation | Names such as `Shelly Plus Plug S` are useful display names but are not preferable to the hardware code. Never use the device ID containing its MAC suffix. |
| TP-Link Kasa / Tapo | Product models such as `HS110`, `KP115`, `P110`, `P110M`, `L530` | Product label or body, Kasa/Tapo Device Info, HA Device information, official support page | Exclude nicknames and serial numbers. Record a hardware revision only when it is reported as part of the discovery identifier or measurements establish materially different power behavior. |
| Aqara / Xiaomi | Printed manufacturer model codes such as `LEDLBT1-L01`, `LB-L03E`, `SP-EUC01`, and `ZNLDP12LM` | Official Aqara specifications, manual, declaration or compliance table; product label; then HA Device Info and Aqara's official device list | `lumi.*`, numeric Matter product IDs, and HomeKit model strings are normally discovery aliases rather than canonical product codes. Follow the detailed Aqara guidance below. |
| Arlec | Printed individual-device codes such as `ALD295HA`, `GLD130HA`, and `PC191HA` | Official Arlec product page and specifications, product or packaging label, then HA Device Info and the original profile PR | Pack suffixes such as `P3` and `P5` normally identify a package SKU rather than the physical device, but retain them as aliases when HA can report them. Follow the detailed Arlec guidance below. |
| Athom | Hardware article/model codes such as `LB01-7W-E27` and `PG05V2-AU10A` | Athom product page or label, official Athom firmware configuration, original profile PR, then ESPHome Devices as corroboration | ESPHome project names are split into manufacturer and model by Home Assistant. Preserve the exact resulting values rather than the full dotted project name. Follow the detailed Athom guidance below. |
| Bang & Olufsen / Beoplay | Preserve the exact official product name, such as `Beoplay M5` or `Beosound Edge`, when no printed manufacturer model/type number has been verified | Product label/manual and official Bang & Olufsen support page; then exact HA Device Info and the originating integration | Older speakers can be exposed with values such as `2714 CA16` or `6661 S53`; preserve confirmed exact values as discovery aliases, not automatic canonical article numbers. Follow the detailed Bang & Olufsen guidance below. |
| Bosch | Official device type designations such as `BSHC-1`, `BSP-EZ`, and `BSP-FZ` | Official Bosch product data and manuals; then HA Device Info and the Bosch local API | Values such as `SmartHomeController` and `PLUG_COMPACT` are discovery identifiers rather than preferable canonical type codes. Follow the concise Bosch guidance below. |
| Bose | Official Bose type/model designations such as `416776` and `421650` | Bose owner guides and declarations; then HA Device Info and the SoundTouch device API | Regional product numbers such as `767520-2100` are not preferable canonical IDs. Preserve exact SoundTouch type names and `Bose Corporation` as discovery aliases. Follow the concise Bose guidance below. |
| Cree | Official ordering/model codes such as `BA19-08027OMF-12CE26-1C100` and `CMA19-60W-AL-9TW-GL` | Official Cree documentation, product label, and technical retailer data; then HA Device Info and Zigbee/Tuya diagnostics | Amazon ASINs are retail identifiers. Preserve exact descriptive Zigbee model strings and opaque Tuya model values as discovery aliases when mapped to the measured bulb. Follow the concise Cree guidance below. |
| Dreame / Dreametech | Official radio-equipment or type codes such as `RLS3D` | Dreame declarations, manuals, and product labels; then exact HA Device Info from the Dreame Vacuum integration | Values such as `dreame.vacuum.r2205` are integration discovery identifiers. Product families such as X50 can cover several robot and base-station variants. Follow the concise Dreame guidance below. |
| Dreo | Exact device model codes such as `DR-HAF001S` and `DR-HTF008S` | Dreo security, support, and product pages; product label/manual; then the official Dreo HA integration and current Device Info | The integration's `deviceName` is user-facing and not a model alias. A grouped sibling code such as `DBTF08S` is not an alias without evidence of electrical equivalence. Follow the concise Dreo guidance below. |
| EGLO | Official numeric material numbers such as `110288`, `900053`, `900084`, and `98847` | EGLO technical data sheet and product label; then exact HA Device Info and the original profile PR | AwoX model values such as `33955` and `33957` can be shared by electrically different EGLO products. Preserve confirmed values as discovery aliases and let PowerCalc offer multiple candidates. Follow the concise EGLO guidance below. |
| Elgato | Printed or regulatory hardware model codes such as `20GAK9901`, `20LAB9901`, `20LAA9901`, `20LAC9901`, and `20LAG9901` | Device label and Elgato/Corsair support or regulatory documentation; then exact HA Device Info and the original profile PR | `10...` values can be retail SKUs, while HA often reports a product string such as `Elgato Key Light`. Follow the concise Elgato guidance below. |
| Elgin | Complete printed product codes such as `48BLEDWIFI00`, `48BLED15WIFI`, and `48LSB30WIFI0` | Product label and original profile PR; then official Elgin product data and exact Tuya/Tuya Local diagnostics | Opaque Tuya model values can be discovery aliases when confirmed for the measured device. Never infer them or add generic `Tuya` as a manufacturer alias. Follow the concise Elgin guidance below. |
| LEDVANCE / OSRAM | Prefer the exact official manufacturer article/model code, such as an `AC...` code or an older OSRAM article number. Retain a device-reported Zigbee model such as `CLA60 RGBW Z3` as canonical only when no more specific official article code can be established for the measured hardware. | Official LEDVANCE product datasheet, declaration or catalog; product label; then HA/integration diagnostics and Zigbee signature | Exact protocol model strings, integration-specific IDs, and officially mapped GTINs can be aliases. Follow the detailed LEDVANCE guidance below. |
| Innr | Printed and device-reported codes such as `RB 285 C`, `RS 230 C`, `SP 240` | Official Innr product page or declaration, product label/manual, then HA ZHA/Zigbee device signature | Keep spaces and suffix letters when they are part of the model code. Bundle SKUs and regional sibling models are not aliases by default. Follow the detailed Innr guidance below. |
| Lidl | Printed product/type codes such as `HG06462A`, `HG08131B`, a specific article code, or an IAN-based identifier when that is the only stable label code | Product or packaging label/manual, official Lidl documentation, then current HA Device Info and the integration's raw Zigbee signature | Reject generic Zigbee models such as `TS0502A` and `TS0505B`. Do not assume a raw `_TZ...` string is a manufacturer alias. Follow the detailed Lidl guidance below. |
| WiZ | Prefer the exact WiZ/Signify material or article number (12NC), commonly beginning with `929...`; retain another verified printed manufacturer model when no 12NC can be established | Official WiZ product specifications, product or packaging label, then HA WiZ Device information and the raw `moduleName` | `SHRGB`, `SHRGBC`, `SHTW`, and related `SH...` values are module/configuration codes rather than unique article numbers. Keep confirmed values as intentionally shared discovery aliases. Follow the detailed WiZ guidance below. |
| Sonos | Prefer the exact manufacturer article/model number printed on the product or packaging when it uniquely identifies the measured hardware. Preserve established product-name directories unless a verified canonical migration is intentionally requested. | Product label/packaging and official Sonos documentation; then HA Sonos Device information, where `model_id` comes from the speaker's `modelNumber` | `S...` values are useful discovery aliases when one-to-one with the measured generation, but are not automatically retail article numbers. Product names and S-codes can both be generation-ambiguous. Follow the detailed Sonos guidance below. |
| Sonoff | Printed product codes such as `ZBMINI`, `ZBMINIR2`, and `B02BA60` | Product label/manual, eWeLink or HA Device information, Zigbee device signature | Do not substitute an underlying generic Tuya/Zigbee identifier for a branded Sonoff code. |
| Tuya and white-label devices | No safe universal pattern | Require a branded model from the product label/manufacturer and compare its full Zigbee signature with known devices | Identifiers such as `TS0601`, `TS0505B`, and `_TZE...` values can cover different hardware. Do not add them as a directory or alias unless uniqueness for the measured device is demonstrated. |

## Amazon

Apply these rules when reviewing or normalizing Amazon Echo and Alexa profiles:

1. Prefer the exact physical hardware model printed on the device or established by official or regulatory documentation as the canonical directory ID. Do not use an Amazon Standard Identification Number (ASIN), commonly a ten-character retail code beginning with `B0`, as the canonical model merely because it appears on a product page or order. Add an ASIN to `aliases` only when an integration is also confirmed to report it.
2. Preserve exact Alexa device types such as `A2U21SRK4QGSE1` and `A18O6U1UQFJ0XK` as discovery aliases when they map to the measured hardware. Alexa Media Player may expose a fallback model composed as `<deviceFamily> <deviceType>`, producing values such as `ECHO ...` and `KNIGHT ...`; retain the exact prefixed value when Device Info, diagnostics, integration source, or the original PR confirms it.
3. Amazon serial numbers or device serial numbers (DSNs) are an intentional exception to the universal alias exclusion when the exact value already exists as an Amazon profile alias or is confirmed as a model value required for Home Assistant discovery. Keep it only on the profile for the device from which it was captured, never use it as the canonical directory ID, and never copy or generalize it to sibling profiles. A stable Alexa device type should be added alongside it when available, rather than replacing an established discovery alias.
4. Check every alias against the canonical IDs and aliases of other Amazon profiles. Similar Echo models can have distinct physical codes, such as clock and non-clock variants, and an alias must not point to a sibling profile merely because they share a generation or enclosure.
5. Preserve a verified regional or hardware model variant when the contributor confirms the exact printed label. If an existing code differs by one character from independently documented codes, do not silently normalize it; ask for a label photo or exact transcription before correcting it.
6. Alexa speakers may reject the measurement tool's directly streamed test MP3 and play a spoken error instead. Confirm that pink noise or another continuous, documented test signal was actually playing while volume levels were measured. For older profiles created before the tool could disable direct streaming, ask whether playback was started manually, for example through Spotify, when the curve or PR evidence is inconclusive.
7. Use concise product names with consistent generation formatting, such as `Echo Dot (Gen3)` and `Echo Show 8 (Gen2)`. Distinguish variants such as `with clock` only when they represent different physical models and profiles.

When an Amazon hardware code, ASIN, Alexa device type, family-prefixed model, or serial discovery value cannot be reconciled, keep the established profile available and ask for the product-label code, exact Home Assistant Device Info fields, originating integration, and measurement playback method.

## Apple

Apply these rules when reviewing or normalizing Apple HomePod profiles:

1. Prefer Apple's printed `A...` hardware model number as the canonical directory ID when official Apple regulatory data or an information guide maps it uniquely to the measured generation. For example, `A2374` identifies HomePod mini and `A2825` identifies HomePod (2nd generation). Do not derive an A-number from a similar product or generation name alone.
2. Distinguish the hardware model number from Apple's regional and color-specific order/SKU codes, commonly beginning with `M`, and from internal identifiers such as `AudioAccessory5,1` and `AudioAccessory6,1`. A code such as `MQJ83` identifies an orderable HomePod variant rather than the generation-wide hardware model, so it is not preferable as the canonical directory ID.
3. Home Assistant's Apple TV integration normally exposes the pyatv `model_str` result as the Device Info model. Preserve the exact reported strings, including capitalization, as aliases: current mappings include `HomePod Mini` and `HomePod (gen 2)`. Treat a raw `AudioAccessory...` value as an alias only when Device Info or diagnostics show that Home Assistant actually exposed it, because Home Assistant uses the raw value only when pyatv cannot identify the model.
4. Add an established marketing name or SKU to `aliases` only when it is a genuine discovery value. For example, pyatv reports `HomePod Mini`, while an order code such as `MQJ83` should not be an alias when Device Info instead reports `HomePod (gen 2)`.
5. Do not add every color or regional SKU as an alias merely because those variants share the same A-number. A cosmetic variant may share the profile when the hardware model and electrical behavior are the same, but its order code is useful for discovery only when an integration reports that exact code.
6. Use Apple's product capitalization in the display name, notably `HomePod mini`. Keep generation formatting consistent with the library, while preserving the integration's exact casing separately in `aliases` when it differs.
7. Verify speaker measurement provenance in the original PR. If the contributor manually changed volume, started pink or white noise, and used the utility only to average each level, set `measure_method` to `manual`, describe the signal, increments, and averaging duration, and remove script settings that did not control the playback or level sequence.

When the A-number, order code, internal identifier, and Home Assistant model cannot be reconciled, keep the established profile available and ask for the bottom-label model number, exact Device Info model, originating integration, and product generation before renaming or adding aliases.

## 3A Smart Home / Nue

Apply these rules when reviewing or normalizing 3A Smart Home and Nue profiles:

1. Treat device-reported codes such as `LXN60-LS27-Z30` and `LXT56-LS27LX1.7` as Zigbee hardware evidence, not automatic proof of the complete product's canonical article code. In particular, an `LXT...` controller identifier can be exposed by both a complete downlight and a standalone RGBW strip controller.
2. Prefer the exact product-specific code printed on the complete light, dimmer, or packaging when it can be verified. An apparent OEM family code such as `WL-SD001-9W` or `WL-SD001-12W` is only a lead until the contributor confirms it on the measured product; verify wattage and, for downlights, lumen output and cut-out size before mapping it.
3. Retain an existing `LXN...` or `LXT...` value in `aliases` when Home Assistant or the originating integration actually reports it. A confirmed shared controller alias may occur on multiple profiles so PowerCalc can offer the matching candidates; never use that shared alias alone to merge measurements or claim hardware equivalence.
4. Preserve complete suffixes and revisions such as `.1` and `.3`. Do not assume sibling controller codes identify equivalent dimmers or share self-usage merely because the base code and product description match.
5. Accept `3A Smart Home DE` and other manufacturer aliases only when the exact value appears in Home Assistant Device Info for the originating integration. Do not generate capitalization variants solely for completeness or infer aliases from a raw signature without confirming how Home Assistant exposes it.
6. Use the branded product line, such as `Nue`, and the verified product type in `name`; omit the generic word `Smart`, the protocol name `ZigBee`, and the manufacturer name when they add no product distinction. Format ratings with a space, for example `Nue RGBW Downlight (9 W)`.

When a controller identifier and apparent product code cannot be reconciled, keep the established profile unchanged and ask for a product-label or packaging photo plus the exact Home Assistant manufacturer, model, originating integration, wattage, and relevant physical specifications.

## Aqara / Xiaomi

Apply these rules when reviewing or normalizing Aqara profiles:

1. Prefer the exact manufacturer model code printed on the product or established by official Aqara specifications, manuals, declarations of conformity, or compliance tables as the canonical directory ID. Codes such as `LEDLBT1-L01`, `LB-L01D`, `LB-L03E`, `PS-S02E`, `SP-EUC01`, and `ZNLDP12LM` take precedence over protocol or integration identifiers.
2. Treat stable Zigbee identifiers such as `lumi.light.agl006` and `lumi.plug.maeu01`, numeric Matter product IDs such as `6145` and `6150`, and HomeKit model strings such as `AL039` as discovery aliases. Add them only when Home Assistant Device Info, diagnostics, the original profile PR, or Aqara's official device list maps the exact value to the measured hardware variant.
3. Do not assume that a numeric Matter product ID, a `lumi.*` value, or a marketing name uniquely identifies the physical product. Cross-check fitting, color capabilities, region, and variant; for example, Aqara's E26, E27, and GU10 LED Bulb T2 variants have distinct product codes and protocol identifiers.
4. Where an official product page groups regional suffixes such as `D` and `E`, use the exact variant reported for the measured device as canonical. Add a sibling suffix as an alias only when evidence shows Home Assistant reports it for compatible hardware whose measurements are valid for the profile; a shared product-family listing alone is insufficient.
5. Normalize obvious presentation artifacts only when another authoritative manufacturer source confirms the intended code. For example, a specifications page may render `SP - EUC01`, while an official compliance table establishes `SP-EUC01`. Do not silently repair a conflicting character, suffix, or digit without corroboration.
6. Keep a former integration-derived value in `aliases` when it remains a genuine discovery value, such as a reported `lumi.*` identifier. Do not retain a corrected typo such as `PS-S020E` as an alias.
7. Use Aqara's concise official product description in `name`, omitting the manufacturer. Keep variant details that distinguish hardware, such as fitting and `RGB CCT`, but remove label-style specifications and marketing prose. Add a product name to `aliases` only when the originating integration actually exposes that exact string as its model value.

When the printed model, protocol identifier, Matter product ID, and Home Assistant model cannot be reconciled, keep the established profile available and ask for the product-label code, exact Device Info fields, originating integration, fitting, region, and light capabilities before renaming or sharing measurements.

## Arlec

Apply these rules when reviewing or normalizing Arlec Grid Connect profiles:

1. Prefer the exact model code of the individual physical device as the canonical directory ID. For example, use `ALD295HA` for the single downlight and `GLD130HA` for the bulb itself rather than a retail multipack SKU.
2. Treat suffixes such as `P3`, `P5`, and `-4` as possible pack quantities, not automatically as part of the device model. Verify their meaning on an official Arlec product page, packaging, or the physical label; do not remove a suffix based on its shape alone.
3. If Home Assistant Device Info, diagnostics, or the original profile PR shows that a pack SKU is reported as the model, add that exact value to `aliases` even though it is not canonical. An alias may intentionally occur on more than one compatible profile when Powercalc must offer the user a choice; do not infer measurement equivalence from the shared alias.
4. Keep a former pack SKU in `aliases` when it remains a real or documented Home Assistant discovery value.
5. Do not add generic Tuya or Grid Connect platform values, raw Tuya manufacturer strings, or `Tuya` as a manufacturer alias merely because the product uses that ecosystem. Require the exact manufacturer and model values exposed by Home Assistant for the measured device.
6. Use concise official Grid Connect product wording in `name`, omitting `Arlec` and cosmetic color. Preserve distinguishing capabilities, fitting, and ratings, with consistent forms such as `RGB+CCT`, `CCT`, `E27`, `B22`, `9 W`, `740 lm`, and `92 mm`.
7. For power adaptors, verify whether the exact model has an energy meter before setting `only_self_usage`. Do not transfer that flag between visually similar plugs: metering models can use `only_self_usage: true`, while a non-metering socket or USB charger must use `false`.

When an individual code, pack SKU, or integration-reported value cannot be reconciled, keep the established profile available and ask for the product or packaging label plus the exact Home Assistant manufacturer, model, model ID, and originating integration.

## Athom

Apply these rules when reviewing or normalizing Athom ESPHome and Tasmota profiles:

1. Prefer the exact hardware article or model code as the canonical directory ID, for example `LB01-7W-E27` for the legacy 7W E27 bulb and `PG05V2-AU10A` for the Australian V2 10 A plug. Distinguish the hardware code from a firmware-specific suffix such as `-TAS` or `-ESP`, a retail bundle suffix, and an ESPHome node or project name.
2. Verify that the code identifies the measured generation and region. Athom reuses product pages and firmware configurations across revisions and countries, and an older page can contain a legacy article number alongside specifications for newer hardware. Corroborate conflicting pages with the product label, original PR evidence, electrical specifications, an official firmware configuration, and an established device catalog before migrating a profile.
3. Treat ESPHome's dotted `project.name` as two discovery fields. Home Assistant splits `<manufacturer>.<model>` and exposes the first segment as the manufacturer and the second as the model. For `athom.rgbww-light`, use `athom` and `rgbww-light`; do not add the full `athom.rgbww-light` string as a model alias unless separate Device Info evidence shows it was exposed intact.
4. Preserve both historical and current project-derived discovery values when official Athom firmware changed them. For example, a current project name such as `China Athom Technology.Athom RGBCW Bulb` supports `China Athom Technology` in `manufacturer.json` and `Athom RGBCW Bulb` in the bulb's `aliases`, while the historical model `rgbww-light` remains an alias for older firmware.
5. Keep a former project-derived value in `aliases` when Home Assistant actually reports the same value as the model; do not preserve a purely internal slug as a discovery alias.
6. Keep manufacturer aliases exact. Values such as `Athom_Technology` from original Device Info and `China Athom Technology` from current official ESPHome project names are valid when the corresponding integration exposes them. Do not invent spacing, capitalization, or underscore variants.
7. Use concise product wording in `name`, omit the manufacturer, and retain distinguishing region, generation, fitting, power, and lumen details. Follow Athom's compact wattage style where it identifies the product, for example `7W E27 RGBCCT Bulb for ESPHome (600 lm)` and `Smart Plug AU V2 (10 A)`.
8. Set `only_self_usage: true` only for an exact Athom plug model with a built-in consumption meter. Recheck the hardware revision and regional code because similarly named plugs can use different metering chipsets or current ratings.

When an Athom article code, hardware revision, firmware project name, and Home Assistant Device Info cannot be reconciled, preserve the established profile and ask for the product label, exact region and revision, firmware type, and current Home Assistant manufacturer and model.

## Bang & Olufsen / Beoplay

Apply these rules when reviewing or normalizing Bang & Olufsen speaker profiles:

1. Distinguish the official product name, a printed manufacturer model/type or article code, and the model value reported by an integration. Prefer a verified stable model/type code as canonical when product-label or official manufacturer evidence maps it uniquely to the measured hardware. Otherwise preserve the established official product name as the directory ID rather than promoting an unexplained integration value.
2. Add an exact integration-reported value such as `2714 CA16` for Beoplay M5 or `6661 S53` for Beosound Edge to `aliases` when Home Assistant Device Info, diagnostics, or the original profile PR maps it to the measured speaker. These values preserve discovery but are not proven manufacturer article numbers merely because they look like structured codes.
3. Do not infer a numeric code for sibling products or remove suffixes such as `CA16` and `S53`. Treat the complete string as opaque discovery evidence until a label or official source explains its structure and confirms whether it is generation- or region-specific.
4. Current Mozart devices discovered by Home Assistant's Bang & Olufsen integration use the discovered or selected product model name. An official product-name directory therefore already supports that exact discovery value. A duplicate alias equal to the directory ID is unnecessary, but preserve a genuinely different model string from another integration, including older products exposed through Cast, when evidence shows it is required for discovery.
5. Keep manufacturer values exact. `Bang & Olufsen` is the current Home Assistant integration value. Retain historical or product-brand forms such as `B&O` and `Beoplay` in `manufacturer.json` only when established profile or integration evidence shows they are needed; do not invent punctuation or spelling variants.
6. Because the model is already shown separately, keep `name` concise and descriptive without repeating the directory ID. Prefer a manufacturer-supported product category such as `Wireless Speaker`, `360° Speaker`, `Multiroom Speaker`, or `Bookshelf Speaker`, and avoid subjective slogans such as “powerful” or “premium”. For speaker calibration, investigate unexpected non-monotonic volume curves, but retain a contributor-verified behavior such as device protection reducing output at maximum volume when the original PR documents a repeat measurement and explanation.
When the printed type code, official product name, and integration-reported model cannot be reconciled, keep the established profile available and ask for the product label, exact Home Assistant `manufacturer`, `model`, and `model_id`, the originating integration, and the product generation or variant.

## Bosch

Prefer Bosch's official device type designation as the canonical ID. Preserve exact Home Assistant or Bosch API values such as `SmartHomeController` and `PLUG_COMPACT` in `aliases`. For the Smart Plug Compact profile, use `BSP-EZ` canonically and retain `BSP-FZ` and `PLUG_COMPACT` as aliases because Bosch documents both plug variants together with the same electrical specifications. Use concise display names without repeating `Bosch`.

## Bose

Prefer the numeric type/model designation in Bose's official documentation as the canonical ID. Add a regional product number such as `767520-2100` to `aliases` only if an integration is confirmed to report it. Home Assistant's SoundTouch integration uses `Bose Corporation` as manufacturer and the device API's type value, such as `SoundTouch 10` or `SoundTouch 300`, as model; preserve those exact values as discovery aliases. Use concise names ending in the product type, such as `Wireless Speaker` or `Soundbar`.

## Cree

Prefer Cree's official ordering or model code as the canonical ID; do not use an Amazon ASIN as the directory when a verified Cree code exists. Retain an established ASIN as an alias when it remains useful for exact profile lookup. Preserve exact integration-reported values such as the Zigbee model `Connected A-19 60W Equivalent` or an opaque Tuya model string in `aliases`. A Connected Max device may require `Tuya` in `manufacturer.json`; accept that shared manufacturer alias only with the exact device model alias, so PowerCalc can offer all matching candidates without treating unrelated Tuya devices as Cree. Use concise product names without repeating Cree and format actual power and light output compactly, for example `(7.5W, 800 lm)`.

## Dreame / Dreametech

Prefer the exact type code from Dreame's declaration, manual, or product label as the canonical ID; for example, `RLS3D` identifies the D10 Plus. Preserve the exact `dreame.vacuum.*` value exposed by the Dreame Vacuum integration as a discovery alias. Use `Dreame` as the canonical manufacturer name and retain established integration values such as `Dreametech` and `Dreametech™` as manufacturer aliases. Do not infer a type code from a marketing family: X50 Ultra and X50 Ultra Complete each have several robot and base-station combinations, so request both printed labels, the exact variant, and current HA `manufacturer`, `model`, and `model_id` before migrating a profile.

## Dreo

Use the exact `DR-...` model returned by the Dreo cloud and printed or documented for the device as the canonical ID. The official Dreo HA integration sets manufacturer `Dreo` and model directly from the cloud `model`; its `deviceName` is a device name, not a model alias. Use Dreo's current product mapping for the display name, but do not add marketing names as aliases unless Home Assistant actually reports them as model values. A grouped mapping such as `DR-HTF008S/DBTF08S` establishes a product family, not identical power consumption; add the sibling code as an alias only when official electrical specifications or measurements establish equivalence. For fan profiles, compare calibration plateaus with the integration's supported physical speed count because repeated percentage points within one speed step are expected.

## EGLO

Prefer EGLO's numeric material number as the canonical directory ID and confirm that it identifies the measured variant through an official technical data sheet, the product label, and the original profile evidence. An AwoX value such as `33955` or `33957` is a Zigbee discovery identifier, not necessarily an EGLO article number: the same value may be exposed for lamps with different dimensions, rated power, and consumption. Preserve an exact confirmed AwoX value in `aliases`, including on multiple profiles when necessary, so PowerCalc can offer every matching candidate; never merge profiles or share measurements based on that alias alone. Accept `AwoX` as a manufacturer alias only when Home Assistant Device Info exposes it as the manufacturer. Use the official product family and correct fixture type in `name`, adding a distinguishing dimension where useful, for example `SALOBRENA-Z Ceiling Light (1200x300mm)` or `FUEVA-Z Surface-Mounted Light (285mm)`. Cross-check the LUT peak against EGLO's rated maximum including the driver, and document when multiple identical lights were measured together and the result was divided per device.

## Elgato

Prefer the exact `20...` hardware model printed on the device or established by Elgato/Corsair regulatory documentation. Do not substitute a `10...` retail SKU merely because it appears on an official store or MSRP page. Preserve the exact product string exposed by Home Assistant, such as `Elgato Key Light`, as a discovery alias when it identifies the measured hardware; exclude per-device name suffixes, serial numbers, and MAC addresses. Keep hardware generations separate—for example, original Key Light `20GAK9901` and Key Light MK.2 `20GAK9902` require distinct evidence and must not share calibration merely because their product names are similar. Use concise official product wording in `name` and omit `Elgato`.

## Elgin

Prefer the complete alphanumeric code printed on the bulb or packaging, preserving all zeroes and suffixes. Product-label evidence takes precedence when a historical Elgin URL redirects to a different current wattage or variant. Use the label-rated wattage in concise names such as `Smart Color 10W`, `Smart Color 15W`, and `Smart Color 30W`, and omit `Elgin`. Add an opaque Tuya or Tuya Local model value only when exact HA Device Info, diagnostics, or the original PR maps it to the measured hardware; do not infer sibling values and do not add generic `Tuya` as a manufacturer alias. When HA evidence contains no visible model, ask for the exact `model` and `model_id` plus the originating integration before adding an alias.

## LEDVANCE / OSRAM

Apply these rules when reviewing or normalizing LEDVANCE and OSRAM profiles:

1. Prefer the exact official manufacturer article/model code as the directory ID. LEDVANCE codes such as `AC26447` take precedence over a GTIN, marketing name, integration-specific value, or malformed concatenation when official product data establishes the mapping. Older OSRAM article numbers and device-reported Zigbee model strings remain valid canonical IDs when they are the most specific verified manufacturer identifier available.
2. Confirm the mapping with an official LEDVANCE product page, datasheet, declaration of conformity, catalog, or product label. Use Home Assistant diagnostics, the integration's raw device information, LEDVANCE firmware data, or an established Zigbee catalog to determine which identifiers are actually reported for discovery.
3. Add exact alternative identifiers for the same hardware to `aliases`. These may include another integration's stable model string, an official Zigbee model string, or a GTIN/EAN that official data maps one-to-one to the article. Do not add a transcribed typo or an unverified numeric string as an alias.
4. Keep a malformed former value or purely internal slug out of `aliases` unless an integration is confirmed to report it.
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
4. Zigbee2MQTT can expose one Home Assistant `model_id` that explicitly lists several printed Lidl codes, separated by slashes. PowerCalc already splits such reported values and offers the canonical profiles for the listed codes as separate candidates. Do not add the compound value or another listed code as an alias solely because they share this discovery value, and do not infer electrical equivalence from the grouping. A listed code without its own measured profile remains unsupported. A stale PR value, converter bug, or catalog mapping that was never exposed by Home Assistant is not a discovery alias.
5. Treat raw Zigbee manufacturer strings such as `_TZ...` as signature evidence, not automatically as `manufacturer.json` aliases. Confirm that ZHA, Zigbee2MQTT, or another integration exposes the exact value as the Home Assistant device manufacturer. Remove exact duplicate aliases, but request current Device Info evidence before deleting a distinct historical alias that may still support discovery.
6. Keep hardware variants separate when their printed codes differ unless official documentation and measurements establish electrical equivalence. Codes ending in `A`, `B`, or `C` may represent distinct fittings, shapes, electronics, or capabilities even when a Zigbee catalog groups them.
7. Use the verified product description in `name`. Lidl's product brands such as `Livarno Home`, `Livarno Lux`, and `Silvercrest` may remain because they identify the branded product even though the library manufacturer is Lidl. Normalize capitalization and capability terms, but do not invent details absent from the label, official documentation, or device capabilities.

When a Lidl label code and integration-reported value cannot be reconciled, ask for a product or packaging label photo and the current Home Assistant Device Info fields. Keep the profile discoverable only through identifiers proven specific to the measured variant.

## WiZ

Apply these rules when reviewing or normalizing WiZ and WiZ-powered Philips Smart LED profiles:

1. Prefer the exact WiZ/Signify material or article number (12NC) as the canonical directory ID, commonly a `929...` value. Confirm it on an official WiZ product page, product or packaging label, or equivalent manufacturer documentation. Do not substitute the retail EAN/GTIN for the 12NC or describe an EAN as the model number. Retain another concrete printed manufacturer model, such as a regional alphanumeric code, when no more authoritative 12NC can be established.
2. Home Assistant's WiZ integration derives its displayed `model` from the device `moduleName`. Values such as `SHRGB`, `SHRGBC`, `SHRGB1C`, `SHTW`, and `SHDW1` describe a controller/module configuration and can be shared by products with different fittings, wattages, shapes, or electronics. Do not use such a value as the canonical directory ID when a specific article number is known.
3. Add the exact `SH...` value reported for each measured device to `aliases`, even when another WiZ profile uses the same alias. This is an intentional WiZ exception: without that alias the article-number profile cannot be discovered, and PowerCalc can present all matching profiles for the user to choose from. Require evidence from Home Assistant Device information, diagnostics, the original profile PR, or the raw `moduleName`; do not infer an alias merely from advertised color capabilities.
4. Keep a former `SH...` directory value in `aliases` because it remains a reported discovery identifier. Do not keep a non-reported internal slug as an alias.
5. Never merge profiles merely because they share an `SH...` alias. Establish that they are the same physical product using the exact 12NC, label, official specifications, and where useful an exact EAN mapping. Shared module codes alone are evidence of discovery ambiguity, not hardware equivalence.
6. For confirmed duplicate physical products, consolidate under the verified article number and retain the most credible calibration data. Compare supported modes, LUT completeness, measurement setup, standby power, and peak draw against the rated power. A complete color-temperature and HS measurement reaching a plausible rated draw is normally preferable to an incomplete LUT with an implausibly low maximum; preserve relevant authorship and measurement provenance when consolidating.
7. If the exact article number or duplicate relationship remains uncertain, ask for the product or packaging label, exact Home Assistant Device information, originating integration, and full `moduleName`. Keep the established profile available until the evidence supports a migration; do not invent a regional 12NC suffix from a similar product page.
8. Spell the manufacturer `WiZ`. Use the official product description in `name`, distinguish WiZ-branded and Philips Smart LED products where that branding identifies the product line, and keep EANs and module codes out of the display name unless they materially clarify unresolved source evidence.

## Sonos

Apply these rules when reviewing or normalizing Sonos profiles:

1. Distinguish three identifiers: the existing Powercalc directory ID, the manufacturer article/model number printed on the device or packaging, and the Sonos `modelNumber` commonly formatted as `S...`. Home Assistant's Sonos integration exposes the speaker `modelNumber` as `model_id` and the product name, with the `Sonos ` prefix removed, as `model`. Do not treat the S-code as the printed article number without separate manufacturer evidence.
2. For an existing profile, preserve its directory ID unless the review explicitly establishes and requests a canonical migration. A newly verified S-code belongs in `aliases`; it does not by itself justify renaming the directory.
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
- [Aqara's security and compliance tables](https://www.aqara.com/en/security-certifications/) map official product names to exact model codes and regional variants.
- [Aqara's supported-device list](https://opendoc.aqara.com/en/docs/SDKDevelopment/IOSDevelopmentGuide/Equipmentcontrol/DeviceControlSDKSupportedDeviceList.html) maps product variants to their `lumi.*` and Matter discovery identifiers.
- [Arlec's ALD295HA product page](https://www.arlec.com.au/products/arlec-white-740lm-grid-connect-smart-led-downlight-with-flushed-lens) identifies the individual downlight model.
- [Arlec's ALD295P5HA product page](https://www.arlec.com.au/products/arlec-white-740lm-grid-connect-smart-led-downlight-with-flushed-lens-5-pack) shows the corresponding five-pack SKU.
- [Athom's legacy bulb product page](https://de.athom.tech/blank-1/color-bulb) retains the `LB01-7W-E27` article number, but its current 12W content illustrates why stale pages require corroboration.
- [Athom's official bulb configuration](https://github.com/athom-tech/athom-configs/blob/main/athom-rgbww-light.yaml) and [plug configuration](https://github.com/athom-tech/athom-configs/blob/main/athom-smart-plug-v2.yaml) define the current ESPHome project manufacturer and model values.
- [ESPHome Devices' Athom 7W bulb page](https://devices.esphome.io/devices/athom-e27-7w-bulb/) documents the legacy `athom.rgbww-light` project and measured product specifications.
- [ESPHome Devices' Athom AU V2 plug page](https://devices.esphome.io/devices/athom-smart-plug-pg05v2-au10a/) maps `PG05V2-AU10A` to the historical `athom.smart-plug-v2` project.
- [Home Assistant's ESPHome manager](https://github.com/home-assistant/core/blob/dev/homeassistant/components/esphome/manager.py) splits ESPHome project names into manufacturer and model discovery values.
- [Home Assistant's Bang & Olufsen config flow](https://github.com/home-assistant/core/blob/dev/homeassistant/components/bang_olufsen/config_flow.py) uses the discovered or selected product model for current Mozart devices.
- [Home Assistant's Bang & Olufsen setup](https://github.com/home-assistant/core/blob/dev/homeassistant/components/bang_olufsen/__init__.py) registers the manufacturer as `Bang & Olufsen` and the selected model as device information.
- [The original Beoplay M5 profile PR](https://github.com/bramstroker/homeassistant-powercalc/pull/3969) records `2714 CA16` as its Home Assistant Device Info model.
- [The original Beosound Edge profile PR](https://github.com/bramstroker/homeassistant-powercalc/pull/3967) records `6661 S53` as its Home Assistant Device Info model.
- [Bosch's software and security update table](https://www.bosch-smarthome.com/nl/nl/software-securityupdates/) identifies `BSHC-1` as the first-generation controller's type designation.
- [Bosch's Smart Plug Compact manual](https://www.bosch-smarthome.com/rom/plug-manual) documents `BSP-EZ` and `BSP-FZ` as device type designations with matching electrical specifications.
- [Bose's SoundTouch 10 owner guide](https://assets.bose.com/content/dam/Bose_DAM/Web/consumer_electronics/global/products/speakers/soundtouch_10_wireless_music_system/pdf/785169_og_soundtouch-10-wireless-system_en.pdf) documents type designation `416776`.
- [Bose's SoundTouch 300 owner guide](https://assets.bose.com/content/dam/Bose_DAM/Web/consumer_electronics/global/products/speakers/st_300_product_page/pdf/773965_og_soundtouch-300-soundbar_en.pdf) documents type designation `421650`.
- [Home Assistant's SoundTouch integration](https://github.com/home-assistant/core/blob/dev/homeassistant/components/soundtouch/media_player.py) uses `Bose Corporation` and the device API type for discovery.
- [Cree's Connected bulb FAQ](https://cms.creelighting.com/app/uploads/dlm_uploads/2021/09/faq-connected-oct26_1.pdf) documents the 60W replacement A19 Zigbee bulb and its `4Flow` filament design.
- [Cree's Connected Max support page](https://www.creelighting.com/resources/for-consumers/connected-max-set-up-and-support/) provides official documentation for Connected Max smart bulbs.
- [Dreame's declarations of conformity](https://global.dreametech.com/pages/declaration-of-conformity) map product names to radio-equipment and type codes.
- [The Dreame Vacuum integration entity implementation](https://github.com/Tasshack/dreame-vacuum/blob/master/custom_components/dreame_vacuum/entity.py) exposes the device-reported manufacturer and model to Home Assistant.
- [Dreo's product security policy](https://www.dreo.com/pages/product-security-policy) lists supported products by exact model code.
- [The official Dreo HA integration device mapping](https://github.com/dreo-team/hass-dreoverse/blob/master/README.md) maps exact model codes to current product names and supported speeds.
- [The official Dreo HA integration entity implementation](https://github.com/dreo-team/hass-dreoverse/blob/master/custom_components/dreo/entity.py) exposes the cloud model separately from the device name.
- [EGLO technical data sheets for 900053](https://tools.eglo.com/tds/eng-GB/900053), [900084](https://tools.eglo.com/tds/eng-GB/900084), and [98847](https://tools.eglo.com/tds/eng-GB/98847) identify the material number, product family, fixture type, dimensions, and rated maximum power.
- [The original EGLO 900053](https://github.com/bramstroker/homeassistant-powercalc/pull/4075) and [900084](https://github.com/bramstroker/homeassistant-powercalc/pull/4078) profile discussions document that distinct physical lights can share the AwoX `33955` discovery value.
- [Elgato's Key Light identification guide](https://help.elgato.com/hc/en-us/articles/20935383021965-Elgato-Key-Light-How-to-Identify-if-You-Have-a-Key-Light-or-Key-Light-MK-2) distinguishes original model `20GAK9901` from MK.2 model `20GAK9902`; its [model-number guide](https://help.elgato.com/hc/en-us/articles/360052737551-Finding-Serial-and-Model-Numbers-of-Elgato-Devices) shows where to verify the hardware code.
- [Corsair's Ring Light declaration](https://cwsmgmt.corsair.com/documents/CE-000431AB%20Elgato%20Ring%20Light.pdf) and [Light Strip declaration](https://cwsmgmt.corsair.com/documents/UKCA-000023AA%20Elgato%20Light%20Strip.pdf) establish the regulatory models `20LAC9901` and `20LAA9901`.
- The original [Elgato Key Light](https://github.com/bramstroker/homeassistant-powercalc/pull/967), [Key Light Air](https://github.com/bramstroker/homeassistant-powercalc/pull/860), [Ring Light](https://github.com/bramstroker/homeassistant-powercalc/pull/1499), [Light Strip](https://github.com/bramstroker/homeassistant-powercalc/pull/3197), and [Light Strip Pro](https://github.com/bramstroker/homeassistant-powercalc/pull/3200) profile PRs preserve the exact Home Assistant product-string aliases and profile provenance.
- The original Elgin [48BLEDWIFI00](https://github.com/bramstroker/homeassistant-powercalc/pull/2290), [48BLED15WIFI](https://github.com/bramstroker/homeassistant-powercalc/pull/2291), and [48LSB30WIFI0](https://github.com/bramstroker/homeassistant-powercalc/pull/3436) profile PRs contain product-label wattage/model evidence and, where visible, exact Tuya-reported model values.
- [Innr product pages](https://innr.com/collections/frontpage) list official product names and type numbers.
- [Innr declarations of conformity](https://innr.com/pages/declarations-of-conformity) corroborate exact type codes and regional variants.
- [Apple's NCC product table](https://images.apple.com/tw/nccid/) maps HomePod generations to their A-number hardware models.
- [Home Assistant's Apple TV integration](https://github.com/home-assistant/core/blob/dev/homeassistant/components/apple_tv/__init__.py) uses pyatv's normalized model name unless the model is unknown.
- [pyatv's model conversion](https://github.com/postlund/pyatv/blob/master/pyatv/convert.py) defines the exact HomePod model strings exposed by Home Assistant.
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
