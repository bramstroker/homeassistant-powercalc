# Profile Library Review TODO

This is the focused research backlog for unresolved profile identity, revision, discovery, barcode, and measurement questions found during the manufacturer consistency audit. Manufacturer progress remains tracked in [issue #4616](https://github.com/bramstroker/homeassistant-powercalc/issues/4616); do not duplicate ordinary missing metadata here.

When resolving an item, change it to `[x]` and append the decisive source plus the commit or PR. Add new items only when the uncertainty is concrete and actionable.

## Canonical profiles and duplicates

- [ ] Decide whether `osram/AC03647` and `ledvance/CLA60 RGBW Z3` should be consolidated. Their identity, EAN, specifications and discovery mapping agree, but the HS LUT maxima differ materially at roughly 6.45W and 9.10W. Obtain label photos, firmware and current Device Info from both measured units to distinguish an electrical revision from a measurement issue; preserve `CLA60 RGBW Z3` as an alias and legacy ID if migrated. [Zigbee2MQTT mapping](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/osram.ts), [CSA product record](https://csa-iot.org/csa_product/cla60-rgbw-z3/), [PR #3819](https://github.com/bramstroker/homeassistant-powercalc/pull/3819), [PR #1856](https://github.com/bramstroker/homeassistant-powercalc/pull/1856).
- [ ] Consolidate `signify/548727` into canonical `signify/LCB001`. Zigbee2MQTT establishes that `LCB001` is product `548727`; prefer the better-controlled `548727` LUT but retain LCB001's measured 0.12W standby, and document the mixed provenance. Preserve `548727` as alias and legacy ID. [PR #1014](https://github.com/bramstroker/homeassistant-powercalc/pull/1014), [PR #1008](https://github.com/bramstroker/homeassistant-powercalc/pull/1008).
- [x] Remove the 2m aliases `LST003` and `9290018187B` from the measured 5m `signify/LST004` profile. Its 46.16W LUT confirms the 5m class; the official mapping identifies `9290018186B` as 5m and `9290018187B` as 2m. Add a separately measured 2m profile later if required. [Original measurement](https://github.com/bramstroker/homeassistant-powercalc/commit/dd086b25c2379a398b1266a09ac170c4633683ad), [alias PR #1507](https://github.com/bramstroker/homeassistant-powercalc/pull/1507).
- [ ] Consolidate `lidl/IAN-365267_2101` into canonical `lidl/14156506L`. Prefer the newer IAN LUT, preserve `IAN-365267_2101` as alias and legacy ID, and add EAN `4055334301848`. [PR #3731](https://github.com/bramstroker/homeassistant-powercalc/pull/3731), [PR #3867](https://github.com/bramstroker/homeassistant-powercalc/pull/3867), [manual](https://www.manualslib.com/manual/3542711/Livarno-Home-365267-2101.html?page=17).
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
- [ ] Identify the measured `gosund/SL2` revision. The current EAN maps to a 5m, 12V/1A RGB product, while the LUT reaches 16.1W and includes color temperature, suggesting `SL2-C` or another revision. Obtain packaging, controller and adapter labels; remove the EAN if it does not match the measured revision.
- [ ] Identify the measured revisions of Müller Licht `404005` and `404019` before adding EANs. Müller Licht reused their article numbers and consumer EANs for lower-power revisions, so match dated label specifications to each LUT peak.
- [ ] Resolve `genio/I004544`: the current official page says 850 lm, while the measured profile and original PR identify the same article as 750 lm. Keep the measured value until its packaging revision is established.

## Signify identity and revision questions

- [ ] Correct or confirm the `signify/LCD006` normalized alias: official sources identify 12NC `929003134501`, while the profile currently contains `9290031346`.
- [ ] Identify the exact `signify/LTE002` revision before adding light output or rated power. Older documentation for article `9290022944` gives 5.2W/470 lm, while a current EPREL sheet gives 4W/320 useful lm; obtain the measured label or complete regional article suffix. [Older product sheet](https://d.otto.de/files/90c9ee69-3987-544c-89da-4122997ba0b4.pdf), [current EPREL sheet](https://www.correct.nl/apps/energy-label/api/products/387866/sheets).
- [ ] Identify the exact regional revision of `signify/LCE002` before adding an EAN. Official family documentation maps `929002294203` to 5.3W/470 lm, but available regional barcode mappings conflict; obtain the measured packaging or full article suffix. [Hue catalog](https://www.assets.signify.com/is/content/Signify/Assets/philips-lighting/italy/20201023-hue-catalog.pdf).
- [ ] Resolve `signify/LDT001` power metadata. The official Aphelion page confirms 600 lm and the product EAN, but its published power fields are internally inconsistent and the LUT peaks around 8.05W; establish the measured label/revision before adding `rated_power`. [Official product page](https://www.philips-hue.com/en-in/p/hue-white-ambiance-aphelion-downlight/5900131C5).
- [ ] Identify the exact revision behind `signify/LCA006` before adding an EAN. The measured LUT and older declaration support 9W, while the current product page reuses `929002468801` for an 11W revision and EAN `8719514291171`.
- [ ] Split or identify the aliases in `signify/LTA012`: `929002335105` appears to be a 17W revision, while `9290024720` is documented as 16W/1600 lm.
- [ ] Resolve `signify/LWB014`: raw-model evidence points to North-American E26 article `455295`, but the profile says E27 and uses generic alias `9290011370`.
- [ ] Resolve the E26/E27 conflict in `signify/LWB004`; alias `433714` identifies a North-American E26 article while the profile says E27.
- [ ] Identify the exact revisions for `signify/LTW011` and `signify/LTW015`. Sources conflict between 8W and 9.5W for LTW011, while `9290011998B` covers several LTW015 retail packages.
- [ ] Determine the measured generation represented by `signify/4080248U9`; its aliases span multiple Signe/Gradient Signe generations with different wattages.
- [ ] Establish the bundled bulb revisions for `signify/4080130P6` and `signify/4300631P6` before adding `rated_power`; the fixture articles remained stable across 8.5W, 9W, and 9.5W bulbs.
- [ ] Resolve the duplicate `4033930P7` alias on `signify/LTP001` and `signify/LTP003`. Official data identifies it as the black Fair pendant (`LTP003`); establish the measured identity of `LTP001`, which is named Cher but should use article `4076130P7` or `4076131P7`.
- [ ] Split or identify the aliases in `signify/LTC013`: they combine Aurelle 30x30cm 19W/2000 lm, Aurelle 60x60cm 39W/4000 lm, and an older 30x30cm 28W/2200 lm revision.
- [ ] Split or identify the aliases in `signify/LTC016`: `3216431P5` is 28W/2200 lm, while `929003099301` is 21W/2000 lm.

## Fixture, endpoint, and kit semantics

- [ ] Remeasure only endpoint `_01`, the integrated LED panel, for `signify/5060730P7` and `signify/5060830P7`; their current LUTs measure the complete fixture. Retain the spot endpoint aliases on `LCG002` and record any whole-fixture measurement only as a cross-check. [Issue #2961](https://github.com/bramstroker/homeassistant-powercalc/issues/2961), [PR #1427](https://github.com/bramstroker/homeassistant-powercalc/pull/1427), [PR #1538](https://github.com/bramstroker/homeassistant-powercalc/pull/1538).
- [x] Classify `signify/5061030P7` as the integrated LED panel rather than the complete 2-spot fixture; contributor evidence confirms that only endpoint `_01` was measured. [PR #2833](https://github.com/bramstroker/homeassistant-powercalc/pull/2833).
- [ ] Establish whether the 140 lm EPREL value for `lidl/HG08383A` describes one internal module or the complete five-part fixture; do not multiply it without fixture-level documentation.
- [ ] Determine whether the 85 lm value published for `hampton bay/HB-10521-HS` is per bulb or for the complete 12-light string.
- [ ] Establish whether the Govee H61A1/H61F5 EPREL records describe the internal light source or the complete strip before adding fixture metadata. For H7020/H7021, the official 15/30-bulb counts and 50 lm per bulb establish fixture totals of 750/1500 lm; rated consumption remains unresolved because 12W/24W describes adapter capacity.
- [x] Identify the regional `ledworks/TWS600STP` package before assigning its EAN. The original PR's ASIN maps to `TWS600STP-GUS`, and Twinkly's regional brochure maps that exact 36W package to EAN `8056326673147`; sibling-region barcodes remain excluded. [PR #2724](https://github.com/bramstroker/homeassistant-powercalc/pull/2724), [regional model record](https://device.report/twinkly/tws600stp-gus), [Twinkly brochure](https://blog.festive-lights.com/blog/wp-content/uploads/2021/01/Twinkly-Professional-Brochure-2021.pdf).

## Barcode and discovery mapping

- [ ] Map Lidl `HG06492A`, `HG06492B`, and `HG06492C` to their exact consumer barcodes using label or packaging evidence. Official lists group `4056233505238`, `4056233505245`, and `4056233505252` without suffix mapping, and retailer evidence conflicts; re-check the existing EAN on `HG06492C`.
- [ ] Identify whether `lidl/399629_2110` measured physical model `HG09368` or `HG09369`; community discovery evidence associates the IAN with `HG09369`, but it does not identify the contributor's measured unit. The shared manual gives 38W for both, so obtain its label before assigning an EAN or lumen value. [Community discovery record](https://community.smartthings.com/t/edge-driver-mc-zigbee-light-multifunction-mc/234387?page=26).
- [ ] Obtain exact packaging or manual evidence for `lidl/HG07834B`. An aggregator reports 4.5W, while the LUT reaches about 6.51W and sibling evidence makes a 6.5W/470 lm variant plausible; do not infer specifications from `HG07834A`.
- [ ] Resolve the `lidl/HG08131C` kit barcode and power revision. Candidate EAN `4055334338745` identifies a starter kit, but seller metadata says 9W while the exact EPREL sheet gives 9.5W/806 lm; require readable packaging before assigning the bundle EAN. [Retail listing](https://www.hood.de/i/livarno-home-zigbee-smart-home-starter-kit-mit-gateway-60633535.htm), [EPREL sheet](https://www.lidl.pl/assets/gcpba9f2cf45f5741dd93cc3b6dafa738ef.pdf).
- [ ] Obtain exact label or EPREL evidence for `lidl/HG06463A`; the product image previously linked in its context is labelled `HG06463B` and cannot support the A profile.
- [ ] Verify the package quantity tied to candidate EAN `4056233688771` before assigning it to `lidl/HG06462A`; exact-model listings disagree about whether it is a single lamp or bundle.
- [ ] Find packaging-label evidence before adding IKEA EANs. IKEA product pages expose article numbers, and marketplace “GTINs” currently appear to be transformations of those article numbers rather than verified barcodes.
- [ ] Find an exact product identifier for `ewelight/2APYC-JL01`; `2APYC-JL01` is an FCC ID shared by JL-01, JL-11, JL-02, JL-21, JL-03, JL-31, JL-04, and JL-41. Reverify the current GU10 classification because community evidence for HA model `ZB-CL01` instead describes a 12V/MR16 lamp.
- [ ] Find authoritative metadata for `lsc/3012586`; currently only the Action article number and measured maximum are established.
- [ ] Obtain exact packaging/SKU evidence for `zemismart/moonlamp`; neither the profile nor its original PR identifies a concrete retail model, so specifications and EAN cannot be assigned safely.
- [ ] Identify the exact product variant behind `zengge/AK001-ZJ2104`; the code appears across different power ratings and discovery fingerprints and is not sufficient for metadata by itself.
- [ ] Establish the complete fixture rated power for `genio/I002579`. The exact package confirms EAN `9348641007943` and a 12V/1A adapter, but an independent measurement reports roughly 4.5W maximum; do not store the adapter's 12W capacity as light consumption. [Target product page](https://www.target.com.au/p/mirabella-genio-wi-fi-led-strip-light/68957643), [measured review](https://ausdroid.net/news/2019/07/02/australias-cheapest-retail-smart-led-light-strip-review-mirabella-genio-wi-fi-colour-3-metre-strip/).

## Deferred scopes

- [ ] Review Tuya light profiles in a dedicated final PR; do not mix them into manufacturer-range metadata branches.
- [ ] Revisit the separate LIFX branch/PR and resolve its model/revision questions before merging it into the main consistency series.
