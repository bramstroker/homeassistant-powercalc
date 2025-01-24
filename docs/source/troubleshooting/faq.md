# Frequently asked questions

## What is the difference between power and energy?

**power** is measured in Watt (W) and represents the instantaneous power your device is consuming.
**energy** is measured in kWh or Wh and indicates how much power is used over time. When you have a device is 1000 Watt and you leave it one for one whole hour you have used 1000 Wh or 1 kWh.
Powercalc also uses this terminology to name your sensors. It creates a `_power` and `_energy` sensor by default.

## Why is no power sensor appearing for my light?

- Make sure you have `powercalc:` entry added to your configuration.
- Check if your light model is in the [supported models](https://library.powercalc.nl) list)
- Check the HA logs for errors

## My light is in the supported model list but not discovered. What can I do?

Powercalc scans your HA installation for all devices having a manufacturer and model information.
It tries to match this information against the model_id and aliases shown in the [supported models](https://library.powercalc.nl) list.
Some integrations return different product codes / model id's for the same light which may cause a mismatch. For example Hue and Zigbee2Mqtt.
To have a look at which model was discovered by powercalc you can enable debug logging.
Now look for the lines `Auto discovered model (manufacturer=xx, model=xx)` in the logs, and see if the model id matches.
When it does not match something powercalc known an aliases might be added. You can create an issue for that or better yet provide a Pull Request for the changes.

## I don't see energy appearing in the energy dashboard, why is that?

It can take up to an hour for HA to gather statistics for the energy sensor. So when it is not appearing immediately just wait for a bit.

## How can I setup an energy sensor for a device which has no entity in HA?

You can use [daily energy](../sensor-types/daily-energy.md) for that.

## My device is not supported, what can I do?

The built-in power profiles in powercalc are created by taking measurements using a smart plug. These profiles are submitted by the community, and the actual hardware (light, switch, smart speaker) is needed. Powercalc includes a script to automate this process.
To run this script you'll need the bulb itself, a smart plug , some technical affinity and some time. See [measure](../contributing/measure.md) for some documentation how to do this.

When you can't contribute for whatever reason you can request a new light model on the [discussion section](https://github.com/bramstroker/homeassistant-powercalc/discussions/categories/request-light-models). However it is no certainty if and when it will be added.

Alternatively you can use the [fixed](../strategies/fixed.md) or [linear](../strategies/linear.md) modes for manual configuration to get an approximation.

## Why does Powercalc create additional power sensor for my smart plug?

Powercalc provides profiles for some smart plugs which don't provide their self usage. Even though their consumption is very small, they will add up to your total consumption in your house. So you'll get a power sensor so you'll know how much the smart plug itself uses. Hence the naming `_device_power` and `_device_energy`.
When you don't want these in your installation you can remove them by using the [exclude_device_types](../library/discovery.md#excluding-device-types) option.
