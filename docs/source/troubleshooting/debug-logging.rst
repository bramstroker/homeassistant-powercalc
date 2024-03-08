Debug logging
=============

To analyse issues on your installation it might be helpful to enable debug logging.

You can enable debug logging by going to the Powercalc integration page. You can use the button below.

.. image:: https://my.home-assistant.io/badges/integration.svg
   :target: https://my.home-assistant.io/redirect/integration/?domain=powercalc

Next click :guilabel:`Enable debug logging`

Alternative method
------------------

Add the following to configuration.yaml:

.. code-block:: yaml

    logger:
      default: warning
      logs:
        custom_components.powercalc: debug