# Fan

## JSON

You can use the linear config in combination with the `calibrate` option to define a linear relationship between the percentage (speed) and the power consumption.

```json
{
  "standby_power": 0.3,
  "device_type": "fan",
  "calculation_strategy": "linear",
  "linear_config": {
    "calibrate": [
      "0 -> 1.50",
      "10 -> 2.50",
      "20 -> 4.00",
      "30 -> 7.50",
      "40 -> 10.50",
      "50 -> 12.00",
      "60 -> 15.50",
      "70 -> 18.50",
      "80 -> 20.50",
      "90 -> 25.50",
      "100 -> 30.50"
    ]
  }
}
```

## Measure

Using the [measure utility](../../contributing/measure.md), select `Fan` in the first step of the wizard.
