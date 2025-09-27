# Uninstalling Powercalc

This guide will help you completely remove Powercalc from your Home Assistant installation.

## 1. Remove from Devices & Services

If you have configured Powercalc via the Home Assistant UI, you can remove it from the Devices & Services page:

1. Navigate to **Settings** > **Devices & services**
2. Find the Powercalc integration in the list and click on it
3. Click on the three-dot menu (⋮) in the top right corner of each configuration entry
4. Click "Delete"
5. Repeat for all Powercalc configurations you have set up

## 2. Remove YAML configuration

If you have added Powercalc to your `configuration.yaml` file, you need to remove the relevant configuration lines. Look for any sections related to Powercalc and delete them. For example:

```yaml
powercalc:
  # Your Powercalc configuration here
```

## 3. Remove sources

If you installed Powercalc using HACS (recommended method):

1. Navigate to **HACS**
2. Find Powercalc and click three-dot menu (⋮)
3. Click "Remove"

## 4. Remove Powercalc internal storage files

You may safely remove:

- config/.storage/powercalc_group

## 5. Restart Home Assistant

!!! note
    After uninstalling, all Powercalc virtual power and energy sensors will be removed from your Home Assistant instance. If you were using these sensors in the Energy Dashboard or in automations, you'll need to update those configurations.

## Extra

If you get the error after `Integration not found: Powercalc` after restarting Home Assistant, you probably have some ignored entries.
To fix this, restart HA in safe mode, go to `Devices & Services`, find and remove the ignored powercalc entries, and restart HA again.
