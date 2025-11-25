# Configuration

This section provides an overview of the configuration options available in Powercalc.

## Overview

Powercalc offers various configuration options to customize the behavior of your power and energy sensors. Configuration can be applied globally or per sensor.

## Global Configuration

The [global configuration](global-configuration.md) allows you to set default values that apply to all power and energy sensors. This is useful for setting common parameters across your entire Powercalc setup.

## Per Sensor Configuration

The [sensor configuration](sensor-configuration.md) allows you to customize individual sensors with specific settings. These settings override any global configuration for the specific sensor.

## Additional Configuration Options

Powercalc provides several additional configuration options to fine-tune your setup:

- [Multiply Factor](multiply-factor.md) - Apply a multiplication factor to power values
- [Standby Power](standby-power.md) - Configure standby power consumption
- [Entity Category](entity-category.md) - Set entity categories for your sensors
- [Outlier Filter](outlier-filter.md) - Filter out abnormal power readings
- [Update Frequency](update-frequency.md) - Control how often power values are updated

## Migration

If you're upgrading from a previous version of Powercalc, check the migration guides:

- [New YAML Structure](migration/new-yaml-structure.md)
- [Discovery Configuration](migration/discovery-config.md)
