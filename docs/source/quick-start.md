# Quick Start

## Installation

You could either install with HACS (recommended) or manual.

=== "HACS (recommended)"

    This integration is part of the default HACS_ repository. Just click `Explore and add repository` and search for `powercalc` to install, or use this link to go directly there:

    [![image](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bramstroker&repository=homeassistant-powercalc&category=integration)

=== "Manual"

    Copy `custom_components/powercalc` into your Home Assistant `config` directory.

**Post installation steps**

After you have downloaded the integration you must enable it.
Powercalc supports both GUI and YAML configuration. Depending on your preference, follow the steps below.

=== "GUI (recommended)"

    Add the integration via the Home Assistant GUI:

    [![image](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc)

    Choose `Global Configuration` and follow the wizard to define global options.

!!! tip

    Enabling [analytics](misc/analytics.md) helps the development team understand how Powercalc is being used and prioritize improvements. The data collected is anonymous and includes information like the number of sensors, types of configurations, and device models. You can opt in during the Global Configuration setup.

=== "YAML"

    - Add the following entry to `configuration.yaml`:

       ```yaml
       powercalc:
         enable_analytics: true # optional, remove this line when you don't want to provide analytics
       ```

    - Restart HA

## Set up power sensors

Powercalc includes a built-in library with 600+ measured power profiles, mostly for lighting devices.
These profiles are measured and created by Powercalc users. See the [library website](https://library.powercalc.nl) for the listing of supported devices.

After installation and restart, Powercalc will automatically:

- Scan your Home Assistant installation
- Detect supported devices using their *manufacturer* and *model*
- Offer to create virtual **power (W)** and additionally **energy (kWh)** sensors

If devices are found, you will see prompts as shown below. Click `ADD` to create the sensors.

![Discovery](img/discovery.png)

If no sensors appear:

- Check the Home Assistant logs for Powercalc-related errors
- Optionally enable [debug logging](troubleshooting/debug-logging.md) for detailed discovery info

If your device is not yet supported or if you prefer full manual control, you can configure sensors yourself.
See: [Sensor types](sensor-types/index.md).

!!! tip

    Don’t want automatic discovery? Disable it:

    ```yaml
    powercalc:
      discovery:
        enabled: false
    ```

Refer to [global configuration](configuration/global-configuration.md) for all settings you can do on global level.

## Energy dashboard

To use virtual power sensors in the Energy Dashboard, you need energy sensors.
Powercalc automatically creates a corresponding [**energy sensor**](sensor-types/energy-sensor.md) for each virtual power sensor, no configuration required.

You can add these energy sensors to the energy dashboard under **Settings → Energy → Individual devices**.

If you prefer to manage energy sensors yourself, you can disable automatic creation using:

``` yaml
powercalc:
  create_energy_sensors: false
```

(See [global configuration](configuration/global-configuration.md))

!!! note

    New energy sensors may take some time to appear in the Energy Dashboard, sometimes up to an hour.
    This is normal; just give Home Assistant a bit of time.

[hacs]: https://hacs.xyz/
