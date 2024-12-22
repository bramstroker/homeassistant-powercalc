# Groups

Powercalc provides several options to group individual power sensors into a single one which sums the total.
This can be very useful to get a glance about the consumption of all your lights together for example.

There are several group types available:

- [Custom group](custom.md)

Create a group with a custom name and add individual power and energy sensors to it.
You can also nest groups to create a hierarchy.

- [Domain group](domain.md)

Create a group for all the power entities of a given domain. For example all lights or media players.

- [Subtract group](subtract.md)

Use this group to subtract the power of one or more entities from another entity.

- [Tracked/Untracked group](tracked-untracked.md)

This group is used to get a sum of all tracked or untracked power sensors.

- Standby group

This group is created by default and sum all power when devices are in standby mode.
