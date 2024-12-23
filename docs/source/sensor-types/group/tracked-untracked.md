# Tracked/untracked group

The `Tracked/Untracked` group is a special group designed to monitor the total power consumption of individual power sensors, referred to as the tracked group.

You can also specify a `main_power_sensor`, which will be used to calculate the `untracked` consumption. This is determined by subtracting the power consumption of the tracked group from the total power consumption.

After configuration you'll end up with two additional sensors:

- `sensor.tracked_power`
- `sensor.untracked_power` (only when `main_power_sensor` is specified)

Additionally energy sensors and utility meters can be created for the tracked and untracked group.
Just toggle these options in the configuration screen.

## Create group with GUI

You can create the group with the GUI using this button.

[![config_flow_start](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc)

When this is not working.

- Go to `Settings` -> `Devices & Services`
- Click `Add integration`
- Search and click `Powercalc`

Select `Group` -> `Tracked/Untracked` and follow the instructions.

!!! note

    Powercalc will only allow a single instance of this group in your installation
