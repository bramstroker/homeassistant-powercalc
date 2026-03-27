# Why does Powercalc create additional power sensor for my smart plug?

Powercalc provides profiles for some smart plugs which don't provide their self usage. Even though their consumption is very small, they will add up to your total consumption in your house. So you'll get a power sensor so you'll know how much the smart plug itself uses. Hence the naming `_device_power` and `_device_energy`.
When you don't want these in your installation you can remove them by using the [exclude_self usage](../../library/discovery.md#excluding-self-usage) option.
