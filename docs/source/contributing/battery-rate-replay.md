# Battery-rate draft evaluation

This evaluates the draft for [issue #5090](https://github.com/bramstroker/homeassistant-powercalc/issues/5090)
using the contributor's [v2 CSV bundle](https://github.com/user-attachments/files/34276366/replay_jarvis_bundle_v2.zip).
The replay calls `BatteryRateStrategy.record_reading` and `calculate_power`, the same methods used by the running strategy.
It models battery/status/drying events, exact sample expiry and periodic recalculation;
it does not run the Home Assistant energy sensor itself.

Reproduce from the repository root:

```sh
curl -L --fail https://github.com/user-attachments/files/34276366/replay_jarvis_bundle_v2.zip -o /tmp/powercalc-5090-replay.zip
uv run python -m utils.replay_battery_rate /tmp/powercalc-5090-replay.zip
```

## Interpretation

The ten-minute default estimates **1218.45 Wh** against **1218 Wh** from the plug (**+0.04%**).
The three holdout windows total **305.36 Wh** against **308 Wh** (**-0.86%**).
The original issue's minute-based replay reported -0.2% overall and -0.8% on holdout at the same coefficient.
These are different simulations: the draft uses a fresh initial percentage as the startup reference,
reacts immediately to battery events, and holds its output until the next relevant event or timer tick.
Percentage increments now expire at their exact window boundary. The previous 60-second-only
timer held increments too long, producing **+1.42%** overall error and **+1.26%** holdout error.
The original replay sampled at one-minute boundaries and suppressed the rate when it had no reading
at the start of the trailing window. The coefficient has not been adjusted to fit this draft.

The steady charging power MAE is **3.64 W**, with **+0.26 W** bias, across counter spans of at least five minutes.
Startup and the last increments around 100% have larger errors. The power comparisons use the 1 Wh-resolution
traces from Oct 22 onward; the earlier two traces have 10 Wh resolution.

A shorter window reduces lag but increases step fluctuations.
A longer window smooths percentage steps but increases startup lag and losses on interrupted charges.
The native ten-minute replay gives **-1.66%** for the recorded mid-run recharge; hypothetical
departure at 30% has **-17.77%** aggregate error. Total error can be positive even when uncounted delayed charging
energy is lost, because coefficient error and baseline contributions also affect the total.

The `Cut at 100% Wh` column removes the rate term at 100% for comparison. The implementation keeps it while the
charging condition holds. `Uncounted charging Wh` measures the remaining positive difference between the gained
percentage times the coefficient and the charging energy already emitted; no correction is applied.
Counter values for hypothetical departures are linearly interpolated between ticks, so those results are estimates.
A complete charge's plug energy uses the last reported counter values at its defined boundaries.

The tables below are a snapshot of the draft replay, without a power clamp, with independent drying power added.
These results support further review and device testing; they do not establish a universal accuracy guarantee.

# Replay results

Fixed coefficient: 0.96 Wh/%, baseline: 3.5 W, drying: +57.2 W. No power clamp or energy compensation.
Fresh window at each charge start. Battery/status/drying events, exact sample expiry and a 60 s timer update power; integration holds power between events.
The first four charges are calibration data; the last three are holdout data. No coefficient is refitted.

## Window: 5 minutes

| Charge | Set | Plug Wh | Native Wh | Error | Cut at 100% Wh |
|---|---|---:|---:|---:|---:|
| Tue 20 | Calibration | 210.0 | 209.25 | -0.36% | 207.76 |
| Wed 21 | Calibration | 260.0 | 263.29 | +1.26% | 261.75 |
| Thu 22 | Calibration | 242.0 | 242.19 | +0.08% | 240.33 |
| Fri 23 | Calibration | 198.0 | 198.36 | +0.18% | 196.46 |
| Sat 24 | Holdout | 96.0 | 97.67 | +1.74% | 96.13 |
| Mon 26 recharge | Holdout | 43.0 | 44.31 | +3.05% | 44.31 |
| Mon 26 final | Holdout | 169.0 | 165.40 | -2.13% | 163.60 |
| **Total** | | 1218.0 | 1220.47 | +0.20% | |

Holdout: 307.38 / 308.0 Wh (-0.20%).

| Power segment | Counter spans >=5 min | MAE W | Bias W |
|---|---:|---:|---:|
| First 15 min | 12 | 8.99 | -8.83 |
| Steady | 102 | 3.93 | +0.08 |
| 100% +/-15 min | 14 | 8.05 | +5.26 |

Hypothetical departures (aggregated Oct 22 onward; counter interpolated between ticks):

| Departure at | Plug Wh | Native Wh before departure | Error | Uncounted charging Wh |
|---|---:|---:|---:|---:|
| 30% | 62.43 | 56.00 | -10.30% | 6.38 |
| 50% | 183.50 | 182.46 | -0.57% | 7.98 |
| 70% | 334.28 | 328.49 | -1.73% | 6.45 |
| 90% | 571.22 | 558.10 | -2.30% | 9.10 |

## Window: 10 minutes

| Charge | Set | Plug Wh | Native Wh | Error | Cut at 100% Wh |
|---|---|---:|---:|---:|---:|
| Tue 20 | Calibration | 210.0 | 209.25 | -0.36% | 206.64 |
| Wed 21 | Calibration | 260.0 | 263.29 | +1.26% | 260.65 |
| Thu 22 | Calibration | 242.0 | 242.19 | +0.08% | 239.70 |
| Fri 23 | Calibration | 198.0 | 198.36 | +0.18% | 194.75 |
| Sat 24 | Holdout | 96.0 | 97.67 | +1.74% | 95.08 |
| Mon 26 recharge | Holdout | 43.0 | 42.29 | -1.66% | 42.29 |
| Mon 26 final | Holdout | 169.0 | 165.40 | -2.13% | 162.90 |
| **Total** | | 1218.0 | 1218.45 | +0.04% | |

Holdout: 305.36 / 308.0 Wh (-0.86%).

| Power segment | Counter spans >=5 min | MAE W | Bias W |
|---|---:|---:|---:|
| First 15 min | 12 | 14.27 | -14.22 |
| Steady | 102 | 3.64 | +0.26 |
| 100% +/-15 min | 14 | 7.46 | +4.58 |

Hypothetical departures (aggregated Oct 22 onward; counter interpolated between ticks):

| Departure at | Plug Wh | Native Wh before departure | Error | Uncounted charging Wh |
|---|---:|---:|---:|---:|
| 30% | 62.43 | 51.33 | -17.77% | 11.04 |
| 50% | 183.50 | 176.35 | -3.89% | 14.09 |
| 70% | 334.28 | 324.17 | -3.03% | 10.78 |
| 90% | 571.22 | 552.95 | -3.20% | 14.26 |

## Window: 20 minutes

| Charge | Set | Plug Wh | Native Wh | Error | Cut at 100% Wh |
|---|---|---:|---:|---:|---:|
| Tue 20 | Calibration | 210.0 | 209.24 | -0.36% | 205.10 |
| Wed 21 | Calibration | 260.0 | 263.29 | +1.26% | 259.38 |
| Thu 22 | Calibration | 242.0 | 242.15 | +0.06% | 238.67 |
| Fri 23 | Calibration | 198.0 | 198.35 | +0.18% | 191.54 |
| Sat 24 | Holdout | 96.0 | 97.67 | +1.74% | 93.83 |
| Mon 26 recharge | Holdout | 43.0 | 38.17 | -11.24% | 38.17 |
| Mon 26 final | Holdout | 169.0 | 165.40 | -2.13% | 161.83 |
| **Total** | | 1218.0 | 1214.27 | -0.31% | |

Holdout: 301.24 / 308.0 Wh (-2.20%).

| Power segment | Counter spans >=5 min | MAE W | Bias W |
|---|---:|---:|---:|
| First 15 min | 12 | 20.35 | -20.35 |
| Steady | 102 | 3.56 | +0.07 |
| 100% +/-15 min | 14 | 6.37 | +3.49 |

Hypothetical departures (aggregated Oct 22 onward; counter interpolated between ticks):

| Departure at | Plug Wh | Native Wh before departure | Error | Uncounted charging Wh |
|---|---:|---:|---:|---:|
| 30% | 62.43 | 43.83 | -29.79% | 18.54 |
| 50% | 183.50 | 163.78 | -10.75% | 26.67 |
| 70% | 334.28 | 314.13 | -6.03% | 20.81 |
| 90% | 571.22 | 545.63 | -4.48% | 21.57 |
