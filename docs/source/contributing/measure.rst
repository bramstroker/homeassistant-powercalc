## Warning!

Incorrect use of electrical and measuring devices carries a risk of electric shock (electrocution). It can cause serious injury or even death!

## Preparation

To start measuring you'll need the following:

- A computer (Windows, Linux, MacOSX) with Python 3.8 or higher
- Supported smartplug which can accurately measure small currents (Shelly, Kasa/Tapo, todo other recommendations)
- A fixture in which you can fit your light and a power plug on the other end which you can connect to your smartplug (TODO, add some pictures)

## Taking measurements

A script is available which will walk through different brightness and color settings and take measurements with your smart plug.
The script can be found at the following location: https://github.com/bramstroker/homeassistant-powercalc/tree/master/utils/measure
Follow the [readme](https://github.com/bramstroker/homeassistant-powercalc/tree/master/utils/measure/README.md) to get the script up and running.

Before you are going to take the actual measurements you have to select a `POWER_METER` and `LIGHT_CONTROLLER` by editing the `.env` file. You also need to set the credentials and information depending on which power meter and light controller you are using.

> NOTE: make sure you temporarily pause possible automations you have in HA for your lights, so the light won't be switched in the middle of measuring session.

Next, you'll need to take note of the `supported_color_modes` of the light you are about to measure. You can find that in "Developer tools" -> "States". Search for your entity there and look at the attributes column. For each of the supported color modes you need to run the measure tool.
When the `xy` is in the supported modes you'll need to choose `hs` in the measure tool, as this is just another representation of a color.

Now start the script to begin the measurements:

`python3 measure.py`

The script will ask you a few questions and will start switching your light to all kind of different settings.
Depending on the selected color mode and sleep settings this will take a while. Somewhere from a few hours to 2 days.

### Troubleshooting
#### Tuya power plug will not connect
For Tuya measuring devices, disable or delete the plug from local tuya and reboot the plug as they only support 1 connection at a time.

#### The globe is not reading on my power meter

Sometimes, measuring multiple of the same light is required to get an accurate set of readings.

To do this, use the [group integration](https://www.home-assistant.io/integrations/group/) - ensure your lights are configured in an identical fashion.

#### Which color modes do I measure?

The best way to tell if unclear, particularly for Tuya based light models, is to check the raw contents of your `config/.storage/core.entity_registry` to find the `supported_color_modes` entry for your device.

Note: some lights incorrectly claim multiple modes which are incompatible. ie; Hue/Sat and Brightness. This conflicts with the HomeAssistant light model guidance.
For now, record for all modes, but submit a bug upstream.

## Measure smart speakers

Version 1.2.0 of the measure script fully automates the measurement session for smart speakers. Just select "Smart speaker" in the first step of the wizard.

## Prepare / finalize the files

When the script has finished you can find the actual files in `/utils/measure/export` directory.

You can inspect the CSV files for correctness by checking for 0 values or large inconsistencies.
When everything looks fine you can safely remove the CSV file (only keep the .csv.gz file) as this is not needed when submitting to the repository.

Next create a manufacturer and model folders in data directory and copy the files there. See the other directories for examples how this is structured.

## Submitting your work with a Pull Request

To create a PR you first have to fork the repository (make your own copy). You can do that with the fork button on the top right.


### Common Problems

Some power sensors, such as Arlec PC191HA, PC287HA appear not able to sense small amounts of current/power.