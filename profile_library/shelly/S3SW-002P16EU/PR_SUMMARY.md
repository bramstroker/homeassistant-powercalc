Title: Add Shelly 2PM Gen3 (S3SW-002P16EU) self-consumption profile

## Summary

Add a device-level `multi_switch` profile for the Shelly 2PM Gen3 with `only_self_usage: true` and eight manually selected WLAN/BT/ECO/AP configurations. The profile calculates one shared device baseline plus an increment for each active relay. Connected load consumption remains with the device's existing metering sensors.

The parent profile uses WLAN values (0.620 W baseline, 0.330 W per active relay). Every subprofile explicitly overrides both values. The profile targets two-relay switch mode; cover mode has not been validated. The Shelly manufacturer metadata included in the local package is copied from upstream and does not require a PR change if already present.

## Measurements

Measured on 2026-10-02 using a Shelly Plug S, with 60-second means for all four relay states. The final WLAN+ECO run used an approximately 9.1 W parallel dummy load, separately measured as a 60-second mean and subtracted from every total. This yields a 0.595 W baseline and a 0.2075 W relay increment. Two earlier WLAN+ECO runs with a zero baseline are excluded. The latest repeat is used for WLAN+AP+ECO.

Relay increments are recalculated as `(P11 - P00) / 2` from reported means, preserving half-milliwatt arithmetic results rather than copying rounded candidates. The source instrument's accuracy is not inferred from these digits. The largest absolute model residual is 0.11 W for one relay state in WLAN+AP+ECO. Dummy baseline precision and low-power meter accuracy limit the results; firmware and settling times were not recorded.

| Subprofile | Baseline W | Increment per relay W |
|---|---:|---:|
| wlan | 0.62 | 0.33 |
| wlan_bt | 0.655 | 0.3025 |
| wlan_eco | 0.595 | 0.2075 |
| wlan_bt_eco | 0.44 | 0.2925 |
| wlan_ap | 0.675 | 0.2925 |
| wlan_ap_bt | 0.7 | 0.315 |
| wlan_ap_eco | 0.64 | 0.31 |
| wlan_ap_bt_eco | 0.655 | 0.3025 |

## Validation

- Manufacturer and parent JSON validated against upstream Draft 2020-12 schemas.
- All eight effective profiles validated after applying their overrides to the parent.
- All four calculated relay states checked for every subprofile; baseline and both-on states reproduce the selected measurements after dummy subtraction.
- ZIP checked for direct extraction to `/config/powercalc/profiles/` with `shelly/` at its root.
- Home Assistant runtime validation has not been performed.

## Submission

Copy `shelly/S3SW-002P16EU/` into the repository's `profile_library/shelly/` directory. Use this text as the PR description and attach the measurement record. `PR_SUMMARY.md` is submission aid and may be omitted from the repository commit. No author name, GitHub handle, firmware or voltage was invented. No pull request has been opened by this package creation task.
