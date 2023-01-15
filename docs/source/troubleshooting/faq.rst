==========================
Frequently asked questions
==========================

What is the difference between power and energy?
------------------------------------------------

**power** is measured in Watt (W) and represents the instantaneous power your device is consuming.
**energy** is measured in kWh or Wh and indicates how much power is used over time. When you have a device is 1000 Watt and you leave it one for one whole hour you have used 1000 Wh or 1 kWh.
Powercalc also uses this terminology to name your sensors. It creates a `_power` and `_energy` sensor by default.

Why is no power sensor appearing for my light?
----------------------------------------------

- Make sure you have `powercalc:` entry added to your configuration.
- Check if your light model is in the [supported models list](https://github.com/bramstroker/homeassistant-powercalc/blob/master/docs/supported_models.md)
- Check the HA logs for errors

I don't see energy appearing in the energy dashboard, why is that?
------------------------------------------------------------------

It can take up to an hour for HA to gather statistics for the energy sensor. So when it is not appearing immediately just wait for a bit.

How can I setup an energy sensor for a device which has no entity in HA?
------------------------------------------------------------------------

You can use :doc:`/daily-fixed-energy` for that.

My light model is not supported, what can I do?
-----------------------------------------------

New LUT files are created by measuring the light bulbs using an automated script.
To run this script you'll need the bulb itself, a smart plug , some technical affinity and some time. See :doc:`/contributing/measure` for some documentation how to do this.

When you can't contribute for whatever reason you can request a new light model on the `discussion section <https://github.com/bramstroker/homeassistant-powercalc/discussions/categories/request-light-models>`_. However it is no certainty if and when it will be added.

Alternatively you can use the :doc:`/strategies/fixed` or :doc:`/strategies/linear` modes for manual configuration to get an approximation.