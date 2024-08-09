====================
Global configuration
====================

Powercalc provides some configuration which can be applied on a global level. This means any of this configuration option applies to all sensors created with powercalc.
Any configuration you do on a per sensor basis will override the global setting for that sensor.

.. note::
    Sensors created with the GUI do have a configuration set for ``create_energy_sensors``, ``create_utility_meters``, ``ignore_unavailable_state`` and ``energy_integration_method``, changing global configuration will not affect the existing GUI configuration entries, to make it easy to change all of them Powercalc provides a service ``powercalc.change_gui_config``. Refer to `Change GUI configuration service`_.

You can add these options to `configuration.yaml` under the ``powercalc:`` property, like so:

.. code-block:: yaml

    powercalc:
      force_update_frequency: 00:01:00 #Each minute
      power_sensor_naming: "{} Powersensor"
      create_energy_sensors: false

All the possible options are listed below.

+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Name                          | Type     | Requirement  | Default                 | Description                                                                                                                                                                                                                                         |
+===============================+==========+==============+=========================+=====================================================================================================================================================================================================================================================+
| create_domain_groups          | list     | **Optional** |                         | Create grouped power sensor aggregating all powercalc sensors of given domains, see :doc:`/sensor-types/group`                                                                                                                                      |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| create_energy_sensors         | boolean  | **Optional** | true                    | Let the component automatically create energy sensors (kWh) for every power sensor                                                                                                                                                                  |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| create_utility_meters         | boolean  | **Optional** | false                   | Set to `true` to automatically create utility meters of your energy sensors. See :doc:`/sensor-types/utility-meter`                                                                                                                                 |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| disable_extended_attributes   | boolean  | **Optional** | false                   | Set to `true` to disable all extra attributes powercalc adds to the power, energy and group entity states. This will help keep the database size small especially when you have a lot of powercalc sensors and frequent update ratio                |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| disable_library_download      | boolean  | **Optional** | false                   | Set to `true` to disable the Powercalc library download feature, see :doc:'/library/library`                                                                                                                                                        |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| enable_autodiscovery          | boolean  | **Optional** | true                    | Whether you want powercalc to automatically setup power sensors for `supported models`_ in your HA instance.                                                                                                                                        |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| energy_sensor_naming          | string   | **Optional** | {} energy               | Change the name of the sensors. Use the `{}` placeholder for the entity name of your appliance. This will also change the entity_id of your sensor                                                                                                  |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| energy_sensor_friendly_naming | string   | **Optional** |                         | Change the friendly name of the sensors, Use `{}` placehorder for the original entity name.                                                                                                                                                         |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| energy_sensor_category        | string   | **Optional** |                         | Category for the created energy sensors. See `HA docs <https://developers.home-assistant.io/docs/core/entity/#generic-properties>`__.                                                                                                               |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| energy_integration_method     | string   | **Optional** | trapezoid               | Integration method for the energy sensor. See `HA docs <https://www.home-assistant.io/integrations/integration/#method>`__                                                                                                                          |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| energy_sensor_precision       | numeric  | **Optional** | 4                       | Number of decimals you want for the energy sensors. See `HA docs <https://www.home-assistant.io/integrations/integration/#round>`__                                                                                                                 |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| energy_sensor_unit_prefix     | string   | **Optional** |                         | Unit prefix for the energy sensor. See `HA docs <https://www.home-assistant.io/integrations/integration/#unit_prefix>`__. Set to ``none`` for to create a Wh sensor                                                                                 |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| force_update_frequency        | string   | **Optional** | 00:10:00                | Interval at which the sensor state is updated, even when the power value stays the same. Format HH:MM:SS                                                                                                                                            |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| ignore_unavailable_state      | boolean  | **Optional** | false                   | Set to `true` when you want the power sensor to display a value (0 or ``standby_power``) regardless of whether the source entity is available.                                                                                                      |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| power_sensor_naming           | string   | **Optional** | {} power                | Change the name of the sensors. Use the `{}` placeholder for the entity name of your appliance. This will also change the entity_id of your sensor                                                                                                  |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| power_sensor_friendly_naming  | string   | **Optional** |                         | Change the friendly name of the sensors, Use `{}` placehorder for the original entity name.                                                                                                                                                         |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| power_sensor_category         | string   | **Optional** |                         | Category for the created power sensors. See `HA docs <https://developers.home-assistant.io/docs/core/entity/#generic-properties>`__.                                                                                                                |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| utility_meter_types           | list     | **Optional** | daily, weekly, monthly  | Define which cycles you want to create utility meters for. See `HA docs <https://www.home-assistant.io/integrations/utility_meter/#cycle>`__                                                                                                        |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| utility_meter_tariffs         | list     | **Optional** |                         | Define different tariffs. See `HA docs <https://www.home-assistant.io/integrations/utility_meter/#tariffs>`__.                                                                                                                                      |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| include_non_powercalc_sensors | boolean  | **Optional** | true                    | Control whether you want to include non powercalc sensors in groups. See :doc:`/sensor-types/group/include-entities`                                                                                                                                |
+-------------------------------+----------+--------------+-------------------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

Change GUI configuration service
--------------------------------

To change the configuration options for all Powercalc GUI config entries at once you can utilize the service ``powercalc.change_gui_config``.
You can use it to change the configuration for the following options

- create_energy_sensor
- create_utility_meters
- ignore_unavailable_state
- energy_integration_method

You can call this service from the GUI (:guilabel:`Developer tools` -> :guilabel:`Services`).
For example to set ``create_utility_meters`` to yes for all powercalc GUI configurations:

.. code-block:: yaml

    service: powercalc.change_gui_config
    data:
      field: create_utility_meters
      value: 1
