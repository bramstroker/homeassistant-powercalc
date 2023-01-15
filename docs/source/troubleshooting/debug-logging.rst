Debug logging
=============

To analyse issues on your installation it might be helpful to enable debug logging.

Add the following to configuration.yaml:

.. code-block:: yaml

    logger:
      default: warning
      logs:
        custom_components.powercalc: debug