# Profile Library Review TODO

This is the focused research backlog for unresolved profile identity, revision, discovery, barcode, and measurement questions found during the manufacturer consistency audit. Manufacturer progress remains tracked in [issue #4616](https://github.com/bramstroker/homeassistant-powercalc/issues/4616); do not duplicate ordinary missing metadata here.

When resolving an item, change it to `[x]` and append the decisive source plus the commit or PR. Add new items only when the uncertainty is concrete and actionable.

## Canonical profiles and duplicates

- [ ] Decide whether `osram/AC03647` and `ledvance/CLA60 RGBW Z3` should be consolidated. Zigbee2MQTT maps `CLA60 RGBW Z3` directly to `AC03647`, and CSA maps the raw model to the same E27 SKU, but the two LUTs differ materially in HS. Establish the measured revisions and choose the canonical LUT; preserve `CLA60 RGBW Z3` as an alias and legacy ID if migrated. [Zigbee2MQTT mapping](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/osram.ts), [CSA product record](https://csa-iot.org/csa_product/cla60-rgbw-z3/).
- [ ] Consolidate or distinguish `signify/548727` and `signify/LCB001`. Both appear to describe the same 650 lm, 8.5W BR30 with UPC `046677548728`; compare the original measurements before choosing the canonical LUT.
- [ ] Resolve `signify/LST004`: alias `9290018187B` is officially the 2m outdoor lightstrip, while the profile name says 5m; `9290018186B` is the 5m article. Confirm the measured article before adding specs or an EAN. [Signify declaration](https://www.assets.signify.com/is/content/Signify/Assets/hue/global/legal/20240708-philips-hue-outdoor-lightstrip-202407-eu-doc.pdf).
- [ ] Consolidate or deliberately retain both `lidl/14156506L` and `lidl/IAN-365267_2101`. The manual identifies them as the same physical product and article 365267 maps to EAN `4055334301848`; choose a canonical profile and preserve migration/discovery identifiers. [Manual](https://www.manualslib.com/manual/3542711/Livarno-Home-365267-2101.html?page=17).
- [ ] Identify the exact Müller Licht article behind `mueller-licht/ZBT-ColorTemperature`. The generic Zigbee model covers multiple fittings and revisions; request the measured label or original packaging before canonicalizing it.

## Hardware revisions and conflicting specifications

- [ ] Identify the revision measured by `ledvance/73741`. Official specifications say 13.5W and 820 lm, but the LUT peaks around 8.75W. The lumen value and UPC are recorded; hold `rated_power` until the discrepancy is explained. [Official specification](https://assets3.ledvanceus.com/media/resource/original/asset-13122091).
- [ ] Identify the exact revisions for `innr/RB 148 T` and `innr/RB 185 C`. Current retail ratings are respectively 5.3W/470 lm and 9.5W/806 lm, while their LUTs peak around 7.98W and 12.78W.
- [ ] Resolve the conflicting 9W and 10.5W revisions published under `innr/RB 175 W`; use dated label or packaging evidence tied to the measurement.
- [ ] Resolve `innr/RF 263`: exact sources disagree between 350 and 390 lm for the same model/EAN.
- [ ] Identify the measured `sengled/E13-N11` revision. Exact documents conflict between 14W/1050 lm and 14.5W/1200 lm, while the LUT peaks near 12.3W.
- [ ] Split or identify the measured revisions represented by `tp-link/L510` and `tp-link/L530` before adding regional or pack EANs. Suffixes and hardware revisions have different fittings and, for L510, different rated power.
- [ ] Resolve the product identity of `teckin/SB50`; published variants span 7.5W, 8W, and 9W and 800/850 lm, so the `SB50-D` barcode cannot yet be assigned safely.
- [ ] Resolve `sylvania/40A19FILCCLWIFI`: the current name says amber filament/2000K, while LEDVANCE documentation identifies it as the color-changing clear model; the separate amber model is `40A19FILWAWIFI`.
- [ ] Identify the exact `gledopto/GL-S-007Z` hardware/firmware revision before adding lumens; sources report 300, 325, and 300–450 lm and the model code has been reused.
- [ ] Determine whether `melitec/DP15` has a usable barcode for the measured 19W pendant. The same model code is now reused for an unrelated rechargeable floor lamp.
- [ ] Resolve whether `gosund/SL2` is rated 12W total or 12W per metre before adding power or lumen metadata.

## Signify identity and revision questions

- [ ] Correct or confirm the `signify/LCD006` normalized alias: official sources identify 12NC `929003134501`, while the profile currently contains `9290031346`.
- [ ] Identify the exact revision behind `signify/LCA006` before adding an EAN. The measured LUT and older declaration support 9W, while the current product page reuses `929002468801` for an 11W revision and EAN `8719514291171`.
- [ ] Split or identify the aliases in `signify/LTA012`: `929002335105` appears to be a 17W revision, while `9290024720` is documented as 16W/1600 lm.
- [ ] Resolve `signify/LWB014`: raw-model evidence points to North-American E26 article `455295`, but the profile says E27 and uses generic alias `9290011370`.
- [ ] Resolve the E26/E27 conflict in `signify/LWB004`; alias `433714` identifies a North-American E26 article while the profile says E27.
- [ ] Identify the exact revisions for `signify/LTW011` and `signify/LTW015`. Sources conflict between 8W and 9.5W for LTW011, while `9290011998B` covers several LTW015 retail packages.
- [ ] Determine the measured generation represented by `signify/4080248U9`; its aliases span multiple Signe/Gradient Signe generations with different wattages.
- [ ] Establish the bundled bulb revisions for `signify/4080130P6` and `signify/4300631P6` before adding `rated_power`; the fixture articles remained stable across 8.5W, 9W, and 9.5W bulbs.

## Fixture, endpoint, and kit semantics

- [ ] Decide whether `signify/5060730P7`, `signify/5060830P7`, and `signify/5061030P7` represent a primary endpoint or the complete fixture. Their `_01` aliases and LUT maxima do not consistently match official whole-fixture values.
- [ ] Establish whether the 140 lm EPREL value for `lidl/HG08383A` describes one internal module or the complete five-part fixture; do not multiply it without fixture-level documentation.
- [ ] Determine whether the 85 lm value published for `hampton bay/HB-10521-HS` is per bulb or for the complete 12-light string.
- [ ] Establish whether the Govee H61A1/H61F5 EPREL records describe the internal light source or the complete strip before adding fixture metadata; do not use H7020/H7021 adapter capacity as rated power.
- [ ] Verify which regional `ledworks/TWS600STP` suffix and PSU were measured before adding regional EANs; official documents list several suffix-specific barcodes but the power supply can affect the profile.

## Barcode and discovery mapping

- [ ] Map Lidl `HG06492A`, `HG06492B`, and `HG06492C` to their exact consumer barcodes using label or packaging evidence. Official lists group `4056233505238`, `4056233505245`, and `4056233505252` without suffix mapping, and retailer evidence conflicts; re-check the existing EAN on `HG06492C`.
- [ ] Find packaging-label evidence before adding IKEA EANs. IKEA product pages expose article numbers, and marketplace “GTINs” currently appear to be transformations of those article numbers rather than verified barcodes.
- [ ] Find an exact product identifier for `ewelight/2APYC-JL01`; `2APYC-JL01` is an FCC ID shared by JL-01, JL-11, JL-02, JL-21, JL-03, JL-31, JL-04, and JL-41.
- [ ] Find authoritative metadata for `lsc/3012586`; currently only the Action article number and measured maximum are established.

## Deferred scopes

- [ ] Review Tuya light profiles in a dedicated final PR; do not mix them into manufacturer-range metadata branches.
- [ ] Revisit the separate LIFX branch/PR and resolve its model/revision questions before merging it into the main consistency series.
