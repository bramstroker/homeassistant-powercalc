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
| LEDVANCE / OSRAM | Device-reported Zigbee model strings such as `CLA60 RGBW Z3`, or a manufacturer article number when it is the precise stable model | HA ZHA/Zigbee device signature, product label, official product datasheet | A retail GTIN/EAN is not automatically the model identifier. Use it only when it is the stable value reported for discovery or is an established alias for the exact hardware. |
| Innr | Printed and device-reported codes such as `RB 285 C`, `RS 230 C`, `SP 240` | Product label/manual and HA ZHA/Zigbee device signature | Keep spaces and suffix letters when they are part of the model code; do not reduce the directory to the marketing family. |
| Sonoff | Printed product codes such as `ZBMINI`, `ZBMINIR2`, and `B02BA60` | Product label/manual, eWeLink or HA Device information, Zigbee device signature | Do not substitute an underlying generic Tuya/Zigbee identifier for a branded Sonoff code. |
| Tuya and white-label devices | No safe universal pattern | Require a branded model from the product label/manufacturer and compare its full Zigbee signature with known devices | Identifiers such as `TS0601`, `TS0505B`, and `_TZE...` values can cover different hardware. Do not add them as a directory or alias unless uniqueness for the measured device is demonstrated. |

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
