# Changelog

## Unreleased

## 0.4.1 - 2026-08-21

### 🐛 Bug Fixes

- #4563 Fix connectivity issues broken pipe in measure app @bramstroker

## 0.4.0 - 2026-08-21

- #4441 Reduce test suite duplication with shared helpers @bramstroker
- #4473 Document conventional commits @bramstroker
- #4528 Change min_voltage and max_voltage to voltage_range in library @bramstroker

### 🚀 Features

- #4435 Improve UI of view log button @bramstroker
- #4507 Measure multiple lights directly in measure app @bramstroker
- #4508 Add probe for lower power measurements @bramstroker
- #4513 Add session overview to measure app @bramstroker
- #4518 Add playwright tests @bramstroker
- #4519 Add eslint @bramstroker
- #4521 Add measure status sensor to HA @bramstroker

### 🐛 Bug Fixes

- #4449 Fix sonarcloud issues @bramstroker
- #4451 Anable more ruff rules @bramstroker
- #4549 Potential fix for broken connection after 10000 seconds @bramstroker
- #4552 Fix MODE from .env being split into characters when a dummy load is configured @philscottydev

### 🧰 Maintenance

- #4474 ci: harden repository quality gates @bramstroker
- #4479 chore: refresh lockfiles and enable Renovate lock maintenance @bramstroker

## 0.3.0 - 2026-07-31

- #4428 Cleanup typing @bramstroker

### 🚀 Features

- #4430 Add support for Shelly password authentication @bramstroker
- #4432 Add integration of controlled entity to PR body @bramstroker

### 🐛 Bug Fixes

- #4384 Fix sonarcloud issues @bramstroker
- #4392 Handle repeated zero readings in the measure app @bramstroker
- #4393 Copy github code was not always working @bramstroker

## 0.2.1 - 2026-07-25

### 🐛 Bug Fixes

- #4376 Fix cache issues causing app to serve old stale UI @bramstroker

## 0.2.0 - 2026-07-25

### 🚀 Features

- #4347 Guide users from measurement results to profile contributions @bramstroker
- #4369 Implement automatic github PR generation @bramstroker
- #4372 Add support to use direct TpLink Kasa connection @bramstroker

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
