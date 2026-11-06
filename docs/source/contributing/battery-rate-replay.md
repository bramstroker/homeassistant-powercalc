# Battery-rate draft evaluation

This evaluates the draft for [issue #5090](https://github.com/bramstroker/homeassistant-powercalc/issues/5090)
using the contributor's [v2 CSV bundle](https://github.com/user-attachments/files/34276366/replay_jarvis_bundle_v2.zip).
The replay calls `BatteryRateStrategy.record_reading` and `calculate_power`, the same methods used by the running strategy.
It models battery/status/drying events and periodic recalculation; it does not run the Home Assistant energy sensor itself.

Reproduce from the repository root:

```sh
curl -L --fail https://github.com/user-attachments/files/34276366/replay_jarvis_bundle_v2.zip -o /tmp/powercalc-5090-replay.zip
uv run python -m utils.replay_battery_rate /tmp/powercalc-5090-replay.zip
```

## Interpretation

The ten-minute default estimates **1235.35 Wh** against **1218 Wh** from the plug (**+1.42%**).
The three holdout windows total **311.88 Wh** against **308 Wh** (**+1.26%**).
The original issue's minute-based replay reported -0.2% overall and -0.8% on holdout at the same coefficient.
These are different simulations: the draft uses a fresh initial percentage as the startup reference,
reacts immediately to battery events, and holds its output until the next relevant event or timer tick.
Expiry of a percentage increment can be delayed until the next timer tick, adding discretization error.
The original replay sampled at one-minute boundaries and suppressed the rate when it had no reading
at the start of the trailing window. The coefficient has not been adjusted to fit this draft.

The steady charging power MAE is **3.92 W**, with **+1.34 W** bias, across counter spans of at least five minutes.
Startup and the last increments around 100% have larger errors. The power comparisons use the 1 Wh-resolution
traces from Oct 22 onward; the earlier two traces have 10 Wh resolution.

A shorter window reduces lag but increases step fluctuations and the relative effect of the 60-second update timer.
A longer window improves the aggregate energy result in this dataset while increasing startup lag and losses on
interrupted charges. The native ten-minute replay gives **+1.60%** for the recorded mid-run recharge; hypothetical
departure at 30% has **-16.40%** aggregate error. Total error can be positive even when uncounted delayed charging
energy is lost, because coefficient error, timer discretization and baseline contributions also affect the total.

The `Cut at 100% Wh` column removes the rate term at 100% for comparison. The implementation keeps it while the
charging condition holds. `Uncounted charging Wh` measures the remaining positive difference between the gained
percentage times the coefficient and the charging energy already emitted; no correction is applied.
Counter values for hypothetical departures are linearly interpolated between ticks, so those results are estimates.
A complete charge's plug energy uses the last reported counter values at its defined boundaries.

The tables below are a snapshot of the draft replay, without a power clamp, with independent drying power added.
These results support further review and device testing; they do not establish a universal accuracy guarantee.

# Replay results

Fixed coefficient: 0.96 Wh/%, baseline: 3.5 W, drying: +57.2 W. No power clamp or energy compensation.
Fresh window at each charge start. Battery/status/drying events and a 60 s timer update power; integration holds power between events.
The first four charges are calibration data; the last three are holdout data. No coefficient is refitted.

### Window: 5 minutes

| Charge | Set | Plug Wh | Native Wh | Error | Cut at 100% Wh |
|---|---|---:|---:|---:|---:|
| Tue 20 | Calibration | 210.0 | 212.90 | +1.38% | 211.33 |
| Wed 21 | Calibration | 260.0 | 268.00 | +3.08% | 266.15 |
| Thu 22 | Calibration | 242.0 | 246.40 | +1.82% | 244.35 |
| Fri 23 | Calibration | 198.0 | 202.97 | +2.51% | 200.63 |
| Sat 24 | Holdout | 96.0 | 103.02 | +7.31% | 101.44 |
| Mon 26 recharge | Holdout | 43.0 | 47.62 | +10.73% | 47.62 |
| Mon 26 final | Holdout | 169.0 | 168.89 | -0.06% | 166.64 |
| **Total** | | 1218.0 | 1249.79 | +2.61% | |

Holdout: 319.52 / 308.0 Wh (+3.74%).

| Power segment | Counter spans >=5 min | MAE W | Bias W |
|---|---:|---:|---:|
| First 15 min | 12 | 8.42 | -7.98 |
| Steady | 102 | 4.70 | +2.02 |
| 100% +/-15 min | 14 | 8.73 | +5.99 |

Hypothetical departures (aggregated Oct 22 onward; counter interpolated between ticks):

| Departure at | Plug Wh | Native Wh before departure | Error | Uncounted charging Wh |
|---|---:|---:|---:|---:|
| 30% | 62.43 | 58.32 | -6.59% | 4.06 |
| 50% | 183.50 | 189.46 | +3.25% | 1.96 |
| 70% | 334.28 | 337.99 | +1.11% | 0.55 |
| 90% | 571.22 | 572.49 | +0.22% | 0.20 |

### Window: 10 minutes

| Charge | Set | Plug Wh | Native Wh | Error | Cut at 100% Wh |
|---|---|---:|---:|---:|---:|
| Tue 20 | Calibration | 210.0 | 211.38 | +0.66% | 208.65 |
| Wed 21 | Calibration | 260.0 | 266.45 | +2.48% | 263.62 |
| Thu 22 | Calibration | 242.0 | 244.80 | +1.16% | 242.22 |
| Fri 23 | Calibration | 198.0 | 200.85 | +1.44% | 196.87 |
| Sat 24 | Holdout | 96.0 | 100.92 | +5.13% | 98.29 |
| Mon 26 recharge | Holdout | 43.0 | 43.69 | +1.60% | 43.69 |
| Mon 26 final | Holdout | 169.0 | 167.27 | -1.02% | 164.46 |
| **Total** | | 1218.0 | 1235.35 | +1.42% | |

Holdout: 311.88 / 308.0 Wh (+1.26%).

| Power segment | Counter spans >=5 min | MAE W | Bias W |
|---|---:|---:|---:|
| First 15 min | 12 | 14.26 | -14.01 |
| Steady | 102 | 3.92 | +1.34 |
| 100% +/-15 min | 14 | 7.67 | +4.83 |

Hypothetical departures (aggregated Oct 22 onward; counter interpolated between ticks):

| Departure at | Plug Wh | Native Wh before departure | Error | Uncounted charging Wh |
|---|---:|---:|---:|---:|
| 30% | 62.43 | 52.19 | -16.40% | 10.19 |
| 50% | 183.50 | 179.78 | -2.03% | 10.66 |
| 70% | 334.28 | 329.17 | -1.53% | 5.77 |
| 90% | 571.22 | 561.12 | -1.77% | 6.48 |

### Window: 20 minutes

| Charge | Set | Plug Wh | Native Wh | Error | Cut at 100% Wh |
|---|---|---:|---:|---:|---:|
| Tue 20 | Calibration | 210.0 | 210.38 | +0.18% | 206.15 |
| Wed 21 | Calibration | 260.0 | 264.70 | +1.81% | 260.66 |
| Thu 22 | Calibration | 242.0 | 243.46 | +0.60% | 239.94 |
| Fri 23 | Calibration | 198.0 | 199.60 | +0.81% | 192.57 |
| Sat 24 | Holdout | 96.0 | 99.35 | +3.49% | 95.48 |
| Mon 26 recharge | Holdout | 43.0 | 38.67 | -10.07% | 38.67 |
| Mon 26 final | Holdout | 169.0 | 166.38 | -1.55% | 162.56 |
| **Total** | | 1218.0 | 1222.53 | +0.37% | |

Holdout: 304.39 / 308.0 Wh (-1.17%).

| Power segment | Counter spans >=5 min | MAE W | Bias W |
|---|---:|---:|---:|
| First 15 min | 12 | 20.35 | -20.35 |
| Steady | 102 | 3.66 | +0.57 |
| 100% +/-15 min | 14 | 6.36 | +3.69 |

Hypothetical departures (aggregated Oct 22 onward; counter interpolated between ticks):

| Departure at | Plug Wh | Native Wh before departure | Error | Uncounted charging Wh |
|---|---:|---:|---:|---:|
| 30% | 62.43 | 44.02 | -29.49% | 18.36 |
| 50% | 183.50 | 164.90 | -10.14% | 25.54 |
| 70% | 334.28 | 316.18 | -5.41% | 18.76 |
| 90% | 571.22 | 549.44 | -3.81% | 17.76 |
