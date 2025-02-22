# Measure

!!! warning

    Incorrect use of electrical and measuring devices carries a risk of electric shock (electrocution). It can cause serious injury or even death!

## Preparation

To start measuring you'll need the following:

- A computer (running Windows, Linux, MacOSX).
- Supported smartplug which can accurately measure small currents (Shelly PM mini Gen3 recommended)
- A fixture in which you can fit your light and a power plug on the other end which you can connect to your smartplug.
- Install the measure script as described here: <https://github.com/bramstroker/homeassistant-powercalc/blob/master/utils/measure/README.md>

## Taking measurements

!!! important

    Devices must have a unique and specific model identification. Generic model identifiers, which could represent multiple different models, are not acceptable. A common example for this are lights identifying as Tuya TS0505B. This is important for accurate auto-discovery and integration. Devices that are rebranded or sold under different names on platforms like AliExpress may not be suitable for integration, as it's challenging to ensure they are the same across different users. These profiles are not acceptable to get included in Powercalc library, but you are free of course to use them in your own installation.

The measure script will walk through different brightness and color settings and take measurements with your smart plug.

Before you are going to take the actual measurements you have to select a `POWER_METER` and `LIGHT_CONTROLLER` by editing the `.env` file. You also need to set the credentials and information depending on which power meter and light controller you are using.
When you want to use the OCR method see [measure OCR](measure-ocr.md).

Next, you'll need to take note of the `supported_color_modes` of the light you are about to measure. You can find that in `Developer tools` -> `States`. Search for your entity there and look at the attributes column. For each of the supported color modes you need to run the measure tool.
When the `xy` is in the supported modes you'll need to choose `hs` in the measure tool, as this is just another representation of a color.

!!! important

    Make sure you temporarily pause possible automations you have in HA for your lights, so the light won't be switched in the middle of measuring session.

Now start the script to begin the measurement session:

```bash
docker run --pull=always --rm --name=measure --env-file=.env -v $(pwd)/export:/app/export -v $(pwd)/.persistent:/app/.persistent -it bramgerritsen/powercalc-measure:latest
```

The script will ask you a few questions and will start switching your light to all kind of different settings.
Depending on the selected color mode and sleep settings this will take a while. This will take 1 hour to a few hours to complete.
Time to take a cup of coffee.

### Measure smart speakers

Version 1.2.0 of the measure script fully automates the measurement session for smart speakers. Just select `Smart speaker` in the first step of the wizard.

## Prepare / finalize the files

When the script has finished you can find the actual files in `/utils/measure/export` directory.

You can inspect the CSV files for correctness by checking for 0 values or large inconsistencies.
When everything looks fine you can safely remove the CSV file (only keep the .csv.gz file) as this is not needed when submitting to the repository.

Next create a manufacturer and model folders in data directory and copy the files there. See the other directories for examples how this is structured.

## Submitting your work with a Pull Request

To create a Pull Request (PR) on the Powercalc GitHub repository, follow these steps:

1. Fork the repository by clicking on the "Fork" button on the top right of the repository page. This will create a copy of the repository under your own account.
2. Next, upload the directory containing your changes to the profile_library directory of your forked repository. Make sure to keep the manufacturer/model folders intact.
3. If you're familiar with Git, you can also use a Git client to make the changes to your local copy of the repository, commit the changes, and push them to your forked repository on GitHub.
4. Once your changes have been uploaded to your forked repository, go to the original repository and click on the "New Pull Request" button. This will open a new page where you can review the changes and submit the PR for review.
5. Once the PR is submitted, the repository maintainers will review your changes and may request additional changes or merge the PR into the main repository.
6. You should also monitor the PR for any feedback and address them accordingly.

## Common Problems

### Getting lot of 0 readings

Some power sensors, such as Arlec PC191HA, PC287HA appear not able to sense small amounts of current/power.

Sometimes, measuring multiple of the same light is required to get an accurate set of readings.

To do this, use the [group integration](https://www.home-assistant.io/integrations/group/), ensure your lights are configured in an identical fashion.

When this is also not working use one of the recommended smart plugs

You could also use a dummy load. This is a device that consumes a fixed amount of power. This can be used to increase the power consumption of the light, so the power meter can measure it more accurately.

### Tuya power plug will not connect

For Tuya measuring devices, disable or delete the plug from local tuya and reboot the plug as they only support 1 connection at a time.

### KeyError: 'apower' on shelly powermeter

Some smart plugs / power meters do not provide the expected endpoint for Powercalc measure util to retrieve the power consumption.

Known devices which have this issues are:
- Shelly EM Gen3 (S3EM-002CXCEU)

For this device you can simply use the `hass` powermeter to do the measurements through Home Assistant.
