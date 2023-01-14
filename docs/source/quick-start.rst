===========
Quick Start
===========

Installation
------------

You could either install with HACS (recommended) or manual.

HACS
----
This integration is part of the default HACS_ repository. Just click "Explore and add repository" and search for "powercalc" to install.

You *could* also use this link

.. image:: https://my.home-assistant.io/badges/hacs_repository.svg
   :target: https://my.home-assistant.io/redirect/hacs_repository/?owner=bramstroker&repository=homeassistant-powercalc&category=integration

**Post installation steps**

- Restart HA
- Add the following entry to `configuration.yaml`:

.. code-block:: yaml

    powercalc:

- Restart HA final time

Manual
------
Copy `custom_components/powercalc` into your Home Assistant `config` directory.
Also follow the post installation steps mentioned above.

Setup power sensors
-------------------

Powercalc has a built-in library of more than 190 power profiles. Currently, this exists mostly of lights.
These profiles have been measured and provided by users. See [supported models](docs/supported_models.md) for the listing of supported devices.

Powercalc scans your HA instance for entities which are supported for automatic configuration. It does that based on the manufacturer and model information known in HA.
After following the installation steps above and restarting HA power and energy sensors should appear.

Todo:

When this is not the case please check the logs for any errors, you can also enable debug logging (TODO link) to get more details about the discovery routine.

When your appliance is not supported out of the box (or you want to have more control) you have extensive options for manual configuration. These are explained below.

.. note::

    Manually configuring an entity will override an auto discovered entity

.. _HACS: https://hacs.xyz/