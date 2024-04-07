Profile library
===============

The component ships with predefined power profiles for different devices.
You can find the list of supported devices in the `supported models`_ section.
This library will keep extending by the effort of community users.

At startup powercalc will check whether any of your entities are in the library, and will provide a discovered entry for you to setup.
You can also setup Powercalc sensors for a entity manually, choose :guilabel:`Virtual power (library)` in the configuration dialog.

Starting from version 1.12.0 all the power profiles are moved out of the component and are downloaded from the internet on demand.
This way we can roll out updates to the library without the need to update the component.
Also you only need to download the profiles you actually use, saving bandwidth and storage.

#TODO: maybe add option to disable remote loading

For more information about the library structure, See :doc:`structure`.

To contribute see the :doc:`measure <contributing/measure>` section.

Custom models
-------------

If you have a device that is not in the library, you can create a custom model.
When it can be useful to share this model with the community, you can submit it to the library.

Custom models are stored in the ``config/powercalc/profiles`` directory.

You'll need to apply the same structure as the core library, with a subdirectory for the manufacturer and model id.

For example:

.. code-block:: text

    config/
    ├-powercalc/
    │ └-profiles/
    │   ├-tp-link/
    │   │ ├─HS100/
    │   │ │ ├─model.json
    │   │ └─...

.. note::
    Custom models are loaded before the built-in library models, so you can override the library models by creating a custom model with the same manufacturer and model id.