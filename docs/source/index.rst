Welcome to Powercalc documentation!
===================================

**Powercalc** is a custom component for Home Assistant to estimate the power consumption (as virtual meters) of lights, fans, smart speakers and other devices, which don't have a built-in power meter. The consumption of light entities is calculated using different strategies to estimate the power usage by looking at brightness, hue/saturation and color temperature. For other entities a generic calculation can be applied, based on the attributes relevant for that entity.

Check out the :doc:`usage` section for further information, including
how to :ref:`installation` the project.

.. note::

   This project is under active development.

Contents
--------

.. toctree::

   usage
   api
