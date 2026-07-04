# Actions

Powercalc provides actions for maintenance, diagnostics, energy correction, profile library updates, and playbook control.

[![Open your Home Assistant instance and show your action developer tools.](https://my.home-assistant.io/badges/developer_services.svg)](https://my.home-assistant.io/redirect/developer_services/)

You can call these from **Developer tools** > **Actions** in Home Assistant or use them in automations.

| Action | Description |
| --- | --- |
| [`powercalc.activate_playbook`](activate-playbook.md) | Activate a playbook on a Powercalc power sensor. |
| [`powercalc.calibrate_cost`](calibrate-cost.md) | Set a cost sensor to a specific monetary value. |
| [`powercalc.calibrate_energy`](calibrate-energy.md) | Set an energy sensor to a specific kWh value. |
| [`powercalc.calibrate_utility_meter`](calibrate-utility-meter.md) | Set a utility meter sensor to a specific value. |
| [`powercalc.change_gui_config`](change-gui-configuration.md) | Batch change Powercalc GUI config entry options. |
| [`powercalc.debug_group`](debug-group.md) | Inspect a Powercalc group and its member contributions. |
| [`powercalc.get_group_entities`](get-group-entities.md) | Retrieve the member entity IDs of a Powercalc group. |
| [`powercalc.increase_daily_energy`](increase-daily-energy.md) | Add a value to a daily energy sensor. |
| [`powercalc.reload`](reload.md) | Reload all Powercalc config entries. |
| [`powercalc.reset_cost`](reset-cost.md) | Reset a cost sensor to zero. |
| [`powercalc.reset_energy`](reset-energy.md) | Reset an energy sensor to zero kWh. |
| [`powercalc.stop_playbook`](stop-playbook.md) | Stop an active playbook. |
| [`powercalc.switch_sub_profile`](switch-sub-profile.md) | Switch a supported library profile to another sub profile. |
| [`powercalc.update_library`](update-library.md) | Update the profile library and reinitialize discovery. |
