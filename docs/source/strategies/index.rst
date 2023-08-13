========================
Virtual power strategies
========================

.. toctree::
   :hidden:

   fixed
   linear
   lut
   playbook
   wled
   composite

Powercalc provides a lot of calculation methods for your virtual power sensors. They are called strategies.
Each strategy is suitable for another use case. They are explained below. Click on the heading to go to the specific section for more information and configuration examples.

:doc:`fixed`
=====================================================

Suitable when your device has a fixed amount of power when it's turned on.
Can also set a power value per state and use templates.

:doc:`linear`
=======================================================

Use this when you want to set power on a linear scale. Useful for dimmable lights or fans which have different speeds.

:doc:`lut`
=====================

Use a Lookup table to map a given light brighness and color to a power value in Watt. Most of powercalc built-in profiles use this.
You'll need to use the measure utility to create these LUT files.

:doc:`playbook`
=========================================

This can be used to record the power usage of a device over time and playback that recording.
Could be used for example to for programs of your washing machine.

:doc:`wled`
=========================================================

Used for led strips controlled by WLED firmware. WLED integration provides estimated current. Powercalc will create power sensors accordingly.

:doc:`composite`
=========================================================

Combine different strategies