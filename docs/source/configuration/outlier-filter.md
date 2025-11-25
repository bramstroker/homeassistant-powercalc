# Outlier Filter

The outlier filter is a feature in PowerCalc that helps improve the accuracy of energy calculations by filtering out abnormal power readings before they are integrated into the energy sensor.

## What is an Outlier?

In the context of power measurements, an outlier is a value that deviates significantly from the expected range of values. Outliers can occur due to:

- Sensor glitches or communication errors
- Temporary spikes in power consumption
- Incorrect readings from the power sensor

These outliers can skew energy calculations, leading to inaccurate energy consumption data.

## How the Outlier Filter Works

PowerCalc uses a rolling-window outlier detection algorithm based on the median and median absolute deviation (MAD). This approach is more robust to extreme values than methods based on mean and standard deviation.

The algorithm works as follows:

1. **Warm-up Period**: The filter accepts the first `min_samples` values unconditionally to build up its initial window.
2. **Outlier Detection**: After the warm-up period, each new value is evaluated:
   - Values less than or equal to the median are always accepted (allowing for downward transitions, e.g., when a device turns off)
   - Values that exceed the median by less than `max_expected_step` are accepted (allowing for reasonable upward transitions)
   - For larger jumps, the modified Z-score is calculated using MAD, and values with a Z-score greater than `max_z_score` are rejected

This approach ensures that:
- Normal fluctuations in power consumption are accepted
- Sudden drops in power (e.g., when a device turns off) are always accepted
- Reasonable increases in power (e.g., when a device turns on) are accepted
- Only extreme, unexpected spikes are filtered out

## Configuration Options

The outlier filter can be configured using the following options:

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `energy_filter_outlier_enabled` | boolean | `false` | Enable or disable the outlier filter for the energy sensor |
| `energy_filter_outlier_max_step` | number | `1000` | Maximum expected step in power values (in watts) |

These options can be set in your sensor configuration, either through YAML or the GUI.

## When to Use the Outlier Filter

The outlier filter is particularly useful in the following scenarios:

- When your power sensor occasionally reports incorrect spikes
- When you have devices with unstable power readings
- When you want to ensure accurate energy calculations by filtering out anomalous readings

## Example Configuration

Here's an example of how to enable the outlier filter in your sensor configuration:

```yaml
sensor:
  - platform: powercalc
    power_sensor_id: sensor.stove_power
    energy_filter_outlier_enabled: true
    energy_filter_outlier_max_step: 2500  # Set maximum expected step to 2500W
```

With this configuration, any power reading that jumps more than 2500W above the median (unless it's a normal transition) will be considered an outlier and won't be included in the energy calculation.

## Technical Details

Internally, the outlier filter uses the following parameters:

- `window_size`: 30 (number of recent values to consider)
- `min_samples`: 5 (minimum number of samples before outlier detection starts)
- `max_z_score`: 3.5 (maximum allowed modified Z-score)
- `max_expected_step`: Configurable via `energy_filter_outlier_max_step` (default: 1000)

The modified Z-score is calculated as:
```
Z = 0.6745 * (value - median) / MAD
```

Where MAD is the median absolute deviation:
```
MAD = median(|x - median(X)|)
```

This provides a robust measure of how much a value deviates from the typical range.
