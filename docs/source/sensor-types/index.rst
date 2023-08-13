==============
Set up sensors
==============

.. toctree::
   :hidden:

   virtual-power-manual
   virtual-power-library
   group
   daily-energy
   real-power-sensor
   energy-sensor
   utility-meter

You can create new Powercalc sensor either with the GUI or YAML.

In the GUI just click the button to directly add a powercalc sensor:

.. image:: https://my.home-assistant.io/badges/config_flow_start.svg
   :target: https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc

When this is not working.

- Go to :guilabel:`Settings` -> :guilabel:`Devices & Services`
- Click :guilabel:`Add integration`
- Search and click :guilabel:`Powercalc`

After initializing the flow for a new configuration you'll be presented a list with choices:

.. image:: /img/menu_options.png

We will explain the options briefly here. To get more information go to the respective sections in the documentation.

:doc:`Virtual power (manual) <virtual-power-manual>`
=====================================================

Create a virtual power sensor by manual configuration. This is the main feature of Powercalc and the possibilities are endless.

:doc:`Virtual power (library) <virtual-power-library>`
=======================================================

Create a virtual power sensor by selecting from the library of power profiles. See `supported models`_.

:doc:`Group <group>`
=====================

Make a group of different individual powercalc sensors. For example you can get the total usage of your kitchen this way or your full house usage. Also supports sub groups and more.

:doc:`Daily fixed energy <daily-energy>`
=========================================

Use this for non smart devices which are not managed by HA, and which you known there daily kWh consumption of.
This allows you to create an energy sensor for that which you can add to the energy dashboard

:doc:`Energy from real power sensor <real-power-sensor>`
=========================================================

Use this when you have an existing power sensor in your installation, which you want to create energy sensor (and optionally utility meters) for.
This also makes it possible to add the power sensor to a powercalc :doc:`group`.

Energy sensors and utility meters
---------------------------------

When setting up power sensors using the above methods Powercalc can automatically create an :doc:`energy sensor <energy-sensor>` (kWh) and optionally :doc:`utility meters <utility-meter>` (sensors which cycle each hour, week, month).
The can be toggled in the GUI or use the YAML options ``create_energy_sensor`` and ``create_utility_meters`` globally or per sensor.