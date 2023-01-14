=========
WLED mode
=========

Supported domains: ``light``

You can use WLED strategy for light strips which are controlled by [WLED](https://github.com/Aircoookie/WLED).
WLED calculates estimated current based on brightness levels and the microcontroller (ESP) used.
Powercalc asks to input the voltage on which the lightstrip is running and optionally a power factor. Based on these factors the wattage is calculated.

You can setup sensors both with YAML or GUI.
When you use the GUI select :guilabel:`wled` in the calculation_strategy dropdown.

Configuration options
---------------------

| Name              | Type    | Requirement  | Default | Description                                 |
| ----------------- | ------- | ------------ | ------- | ------------------------------------------- |
| voltage           | float   | **Required** |         | Voltage for the lightstrip                  |
| power_factor      | float   | **Optional** | 0.9     | Power factor, between 0.1 and 1.0           |

**Example**

.. code-block:: yaml

    sensor:
      - platform: powercalc
        entity_id: light.wled_lightstrip
        wled:
          voltage: 5