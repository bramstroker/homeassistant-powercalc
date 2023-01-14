Measure
=======

.. warning::
    Incorrect use of electrical and measuring devices carries a risk of electric shock (electrocution). It can cause serious injury or even death!

Preparation
-----------

To start measuring you'll need the following:

- A computer (Windows, Linux, MacOSX) with Python 3.8 or higher
- Supported smartplug which can accurately measure small currents (Shelly, Kasa/Tapo, todo other recommendations)
- A fixture in which you can fit your light and a power plug on the other end which you can connect to your smartplug (TODO, add some pictures)

Taking measurements
-------------------

A script is available which will walk through different brightness and color settings and take measurements with your smart plug.
The script can be found at the following location: https://github.com/bramstroker/homeassistant-powercalc/tree/master/utils/measure
Follow the [readme](https://github.com/bramstroker/homeassistant-powercalc/tree/master/utils/measure/README.md) to get the script up and running.

Before you are going to take the actual measurements you have to select a ``POWER_METER`` and ``LIGHT_CONTROLLER`` by editing the `.env` file. You also need to set the credentials and information depending on which power meter and light controller you are using.

> NOTE: make sure you temporarily pause possible automations you have in HA for your lights, so the light won't be switched in the middle of measuring session.

Next, you'll need to take note of the ``supported_color_modes`` of the light you are about to measure. You can find that in "Developer tools" -> "States". Search for your entity there and look at the attributes column. For each of the supported color modes you need to run the measure tool.
When the ``xy`` is in the supported modes you'll need to choose ``hs`` in the measure tool, as this is just another representation of a color.

Now start the script to begin the measurements:

`python3 measure.py`

The script will ask you a few questions and will start switching your light to all kind of different settings.
Depending on the selected color mode and sleep settings this will take a while. This will take 1 hour to a few hours to complete.

Measure smart speakers
^^^^^^^^^^^^^^^^^^^^^^

Version 1.2.0 of the measure script fully automates the measurement session for smart speakers. Just select "Smart speaker" in the first step of the wizard.

Prepare / finalize the files
----------------------------

When the script has finished you can find the actual files in `/utils/measure/export` directory.

You can inspect the CSV files for correctness by checking for 0 values or large inconsistencies.
When everything looks fine you can safely remove the CSV file (only keep the .csv.gz file) as this is not needed when submitting to the repository.

Next create a manufacturer and model folders in data directory and copy the files there. See the other directories for examples how this is structured.

Submitting your work with a Pull Request
----------------------------------------

To create a Pull Request (PR) on a GitHub repository, follow these steps:

1. Fork the repository by clicking on the "Fork" button on the top right of the repository page. This will create a copy of the repository under your own account.
2. Next, upload the directory containing your changes to the custom_components/powercalc/data directory of your forked repository. Make sure to keep the manufacturer/model folders intact.
3. If you're familiar with Git, you can also use a Git client to make the changes to your local copy of the repository, commit the changes, and push them to your forked repository on GitHub.
4. Once your changes have been uploaded to your forked repository, go to the original repository and click on the "New Pull Request" button. This will open a new page where you can review the changes and submit the PR for review.
5. Once the PR is submitted, the repository maintainers will review your changes and may request additional changes or merge the PR into the main repository.
6. You should also monitor the PR for any feedback and address them accordingly.

Common Problems
---------------

Some power sensors, such as Arlec PC191HA, PC287HA appear not able to sense small amounts of current/power.
Use one of the suggested smart plugs.

#### Tuya power plug will not connect
For Tuya measuring devices, disable or delete the plug from local tuya and reboot the plug as they only support 1 connection at a time.

#### The globe is not reading on my power meter

Sometimes, measuring multiple of the same light is required to get an accurate set of readings.

To do this, use the [group integration](https://www.home-assistant.io/integrations/group/) - ensure your lights are configured in an identical fashion.