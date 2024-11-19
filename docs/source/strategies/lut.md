# LUT

Supported domain: `light`

This is the most accurate mode.
For a lot of light models measurements are taken using smart plugs. All this data is saved into CSV files. When you have the LUT mode activated the current brightness/hue/saturation of the light will be checked and closest matching line will be looked up in the CSV.

There are two possibilities to add virtual power sensors using LUT mode:

1. Predefined light measurements: The component ships with predefined light measurements for some light models. Also see [supported models](https://library.powercalc.nl).
2. Custom light measurements: It is possible to define your own custom light models. See [LUT file structure](../library/structure.md) for details on file and directory structure.

These LUT files are created using the measurement tool Powercalc provides. When you are interested in taking measurements yourself and contribute to the profile library yourself see [measure](../contributing/measure.md).

You can setup sensors both with YAML or GUI.

## GUI

With the GUI select `Virtual power (library)` in the first step. Powercalc should automatically detect the correct manufacturer and model from the device information known in HA.
You can force another manufacturer / model by unchecking the `Confirm model` checkbox, in the next steps you'll be asked to select the manufacturer and model.

## YAML

For most lights the device information in HA will detect the manufacturer and model correctly, so you only need to supply the `entity_id`.

```yaml
powercalc:
  sensors:
    - entity_id: light.livingroom_floorlamp
```

When the correct manufacturer and model could somehow not be discovered from HA, you can supply these manually.
You can also use this option to force using a certain LUT.

```yaml
powercalc:
  sensors:
    - entity_id: light.livingroom_floorlamp
      manufacturer: signify
      model: LCT010
```

Some light models (currently LIFX brand) require you to refer a so called "sub profile" directory, because they have different power charasteristics based on some information not known to HA. For example LIFX BR30 Night Vision light has some infrared mode which can be set in the LIFX app. To load the LUT file for a infrared setting of 25 you can use the following configuration.
You will need to lookup the available sub LUT's in the powercalc data directory.

```yaml
powercalc:
  sensors:
    - entity_id: light.lifx_nighvision
      manufacturer: lifx
      model: LIFX BR30 Night Vision/infrared_25
```
