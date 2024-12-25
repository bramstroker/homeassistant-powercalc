# Smart speaker

Smart speakers are devices that can play music, answer questions, and control smart home devices. They are often used in combination with voice assistants like Amazon Alexa, Google Assistant, or Apple Siri.
Powercalc profiles define power usage per volume level, this will give a pretty accurate indication of the power usage of the device.
However for speakers which have a high power output, the estimated power usage can be a bit off depending on the music played.

## JSON

Example model.json

```json
{
  "calculation_enabled_condition": "{{ is_state('[[entity]]', 'playing') }}",
  "calculation_strategy": "linear",
  "device_type": "smart_speaker",
  "linear_config": {
    "calibrate": [
      "10 -> 1.79",
      "20 -> 1.79",
      "30 -> 1.86",
      "40 -> 1.93",
      "50 -> 1.94",
      "60 -> 2.09",
      "70 -> 2.34",
      "80 -> 2.3",
      "90 -> 2.43",
      "100 -> 2.51",
      "0 -> 1.63"
    ]
  },
  "standby_power": 0.9
}
```

!!! note
    Required fields are omitted in this example for brevity. For the full list of required fields see the [model structure](../structure.md)

## Measure

To integrate a smart speaker with Powercalc, the [measure tool](../../contributing/measure.md) provides a mode to measure it's power consumption.
It does that by playing pink noise at different volumes and measuring the power consumption.

After starting the measure tool, select `Smart speaker` in the first step of the wizard.

The process will take less than 5 minutes to complete.
