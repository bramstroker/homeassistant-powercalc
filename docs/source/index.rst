Welcome to Powercalc documentation!
===================================

**Powercalc** is a custom component for Home Assistant to estimate the power consumption (as virtual meters) of lights, fans, smart speakers and other devices, which don't have a built-in power meter. The consumption of light entities is calculated using different strategies to estimate the power usage by looking at brightness, hue/saturation and color temperature. For other entities a generic calculation can be applied, based on the attributes relevant for that entity.

Follow :doc:`quick-start` for the initial installation / setup

.. note::

   This project is under active development.

Getting Started
***********************

.. toctree::
   :maxdepth: 1

   quick-start
   setup

Configuration
***********************

.. toctree::
   :maxdepth: 1

   virtual-power-manual
   virtual-power-library
   daily-energy
   group
   real-power-sensor
   configuration/global-configuration
   configuration/sensor-configuration
   energy-sensor
   utility-meter
   naming

Troubleshooting
********************

.. toctree::
   :maxdepth: 1

   troubleshooting/debug-logging
   troubleshooting/faq

Contributing
********************

.. toctree::
   :maxdepth: 1

   contributing/measure

