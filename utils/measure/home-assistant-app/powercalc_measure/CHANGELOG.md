# Changelog

## Unreleased

## 0.1.2 - 2026-07-18

### 🐛 Bug Fixes

- #4343 Tolerate malformed Home Assistant entity registry entries @bramstroker

## 0.1.1 - 2026-07-18

- #4341 Auto-discover charging battery source @bramstroker

## 0.1.0 - 2026-07-18

- #4322 Unify power reading validation @bramstroker
- #4323 Pass explicit session execution context @bramstroker
- #4324 Separate app and CLI runtime dependencies @bramstroker
- #4328 Enforce strict typing across the Measure package @bramstroker
- #4329 Load Measure entity selectors from one snapshot @bramstroker
- #4330 Isolate Measure session logs @bramstroker
- #4331 Probe power meters once during preflight @bramstroker
- #4332 Remove unused power meter extension hook @bramstroker
- #4334 Remove the legacy OCR launcher @bramstroker
- #4336 Speed up Measure CI image builds @bramstroker

### 🚀 Features

- #4315 Get rid of release-drafter and implement own drafter @bramstroker

### 🐛 Bug Fixes

- #4316 Stop controlled devices after measurements @bramstroker
- #4317 Support Kasa power meters on Python 3.14 @bramstroker
- #4318 Reject unstable dummy load calibrations @bramstroker
- #4319 Restrict Home Assistant app adapters @bramstroker
- #4320 Normalize generated profile metadata @bramstroker
- #4321 Validate charging battery sources before measurement @bramstroker
- #4325 Prevent Measure release draft update races @bramstroker
- #4326 Show dummy-load calibration lookup failures @bramstroker
- #4327 Bound recorder plot and diagnostics memory @bramstroker
- #4333 Report the Measure app runtime version @bramstroker
- #4335 Block Measure releases with stale notes @bramstroker
- #4337 Warn before loud speaker measurements @bramstroker

## 0.0.1 - 2026-07-17

- Initial version of the new measure tool with Home Assistant app support.
