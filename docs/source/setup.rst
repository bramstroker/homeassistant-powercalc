==============
Set up sensors
==============

You can create new Powercalc sensor either with the GUI or YAML.

In the GUI just click the button to directly add a powercalc sensor:

.. image:: https://my.home-assistant.io/badges/config_flow_start.svg
   :target: https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc

When this is not working.

- Go to :guilabel:`Settings` -> :guilabel:`Devices & Services`
- Click :guilabel:`Add integration`
- Search and click :guilabel:`Powercalc`

After initializing the flow for a new configuration you'll be presented a list with choices:

.. image:: img/menu_options.png

We will explain the options briefly here. To get more information go to the respective sections in the documentation.

Daily Energy
------------
:doc:`daily-energy`

Use this for non smart devices which are not managed by HA, and which you known there daily kWh consumption of.
This allows you to create an energy sensor for that which you can add to the energy dashboard

Group
------------
:doc:`group`

Make a group of different individual powercalc sensors. For example you can get the total usage of your kitchen this way or your full house usage. Also supports sub groups and more.

Virtual power (manual)
----------------------
:doc:`virtual-power-manual`

Create a virtual power sensor by manual configuration. This is the main feature of Powercalc and the possibilities are endless.

Virtual power (library)
-----------------------
:doc:`virtual-power-library`

Create a virtual power sensor by selecting from the library of power profiles. See `supported models`_.

Energy from real power sensor
-----------------------------
:doc:`real-power-sensor`

Use this when you have an existing power sensor in your installation, which you want to create energy sensor (and optionally utility meters) for.
This also makes it possible to add the power sensor to a powercalc :doc:`group`.
