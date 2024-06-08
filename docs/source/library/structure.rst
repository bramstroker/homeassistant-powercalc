Library structure
=================

Each power profile has it's own subdirectory `{manufacturer}/{modelid}`. i.e. signify/LCT010, containing a `model.json` file and optionally CSV files for the LUT calculation strategy.

model.json
----------

Every model MUST contain a ``model.json`` file which defines the supported calculation modes and other configuration.
See the `json schema <https://github.com/bramstroker/homeassistant-powercalc/blob/master/profile_library/model_schema.json>`_ how the file must be structured or the examples below.

When the calculation strategy is ``lut`` also [CSV lookup files](#lut-data-files) must be provided, which can be created by running the measure tool.

Example lut mode:

.. code-block:: json

    {
        "name": "Hue White and Color Ambiance A19 E26 (Gen 5)",
        "standby_power": 0.4,
        "calculation_strategy": "lut",
        "measure_method": "script",
        "measure_device": "Shelly Plug S"
    }

Example linear mode

.. code-block:: json

    {
        "name": "Hue Go",
        "calculation_strategy": "linear",
        "standby_power": 0.2,
        "linear_config": {
            "min_power": 0,
            "max_power": 6
        },
        "measure_method": "manual",
        "measure_device": "From manufacturer specifications"
    }

You can use ``aliases`` to define alternative model names, which will be used during discovery.
This can be helpful when same model is reported differently depending on the integration. For example, the same light bulb could be reported differently by the Hue integration compared to the deCONZ integration.

LUT data files
--------------

For light profiles using the ``lut`` calculation strategy, the power consumption is calculated based on a lookup table.
These lookup tables are saved as CSV files in the model directory.

Depending on the supported color modes of the light the integration expects one or more CSV files here:

 - hs.csv.gz (hue/saturation, colored lamps)
 - color_temp.csv.gz (color temperature)
 - brightness.csv.gz (brightness only lights)

Some lights support two color modes (both hs and color_temp), so there must be two CSV files.

The files are gzipped to keep the repository footprint small, and installation fast but gzipping files is not mandatory.

Example:

.. code-block::

    - signify
      - LCT010
        - model.json
        - hs.csv.gz
        - color_temp.csv.gz

Expected file structure
^^^^^^^^^^^^^^^^^^^^^^^

- The file **MUST** contain a header row.
- Watt value decimal point must be a `.` not a `,`. i.e. `18.4`
- The data rows in the CSV files **MUST** have the following column order:

**hs.csv**

.. code-block:: text

    bri,hue,sat,watt

**color_temp.csv**

.. code-block:: text

    bri,mired,watt

**brightness.csv**

.. code-block:: text

    bri,watt

***Ranges***:

- brightness (0-255)
- hue (0-65535)
- saturation (0-255)
- mired (0-500)  min value depending on min mired value of the light model
