Welcome to Powercalc documentation!
===================================

**Powercalc** is a custom component for Home Assistant to estimate the power consumption (as virtual meters) of lights, fans, smart speakers and other devices, which don't have a built-in power meter. The consumption of light entities is calculated using different strategies to estimate the power usage by looking at brightness, hue/saturation and color temperature. For other entities a generic calculation can be applied, based on the attributes relevant for that entity.

Follow :doc:`quick-start` for the initial installation / setup

.. note::

   This project is under active development.

Contents
--------

.. toctree::

   :maxdepth: 2
   quick-start
   virtual-power
   strategies/*
   configuration/global-configuration
   configuration/sensor-configuration
   group
   naming
   debug-logging

.. toctree::
    caption: Strategies
    strategies/fixed
    strategies/linear
    strategies/lut
    strategies/wled

