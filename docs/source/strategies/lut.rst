===
LUT
===

Supported domain: ``light``

This is the most accurate mode.
For a lot of light models measurements are taken using smart plugs. All this data is saved into CSV files. When you have the LUT mode activated the current brightness/hue/saturation of the light will be checked and closest matching line will be looked up in the CSV.
- [Supported models](#supported-models) for LUT mode
- [LUT file structure](#lut-data-files)

These LUT files are created using the measurement tool Powercalc provides. When you are interested in taking measurements yourself and contribute to the profile library yourself see these intstructions.

You can setup sensors both with YAML or GUI.

GUI
---

With the GUI select :guilabel:`Virtual power (library)` in the first step. Powercalc should automatically detect the correct manufacturer and model from the device information known in HA.
You can force another manufacturer / model by unchecking the :guilabel:`Confirm model` checkbox, in the next steps you'll be asked to select the manufacturer and model.

YAML
----

For most lights the device information in HA will detect the manufacturer and model correctly, so you only need to supply the `entity_id`.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: light.livingroom_floorlamp

When the correct manufacturer and model could somehow not be discovered from HA, you can supply these manually.
You can also use this option to force using a certain LUT.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: light.livingroom_floorlamp
        manufacturer: signify
        model: LCT010

Some light models (currently LIFX brand) require you to refer a so called "sub profile" directory, because they have different power charasteristics based on some information not known to HA. For example LIFX BR30 Night Vision light has some infrared mode which can be set in the LIFX app. To load the LUT file for a infrared setting of 25 you can use the following configuration.
You will need to lookup the available sub LUT's in the powercalc data directory.

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: light.lifx_nighvision
        manufacturer: lifx
        model: LIFX BR30 Night Vision/infrared_25