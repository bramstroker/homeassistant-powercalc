# Debug logging

To analyse issues on your installation it might be helpful to enable debug logging.

You can enable debug logging by going to the Powercalc integration page. You can use the button below.

[![!image](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=powercalc)

Next click `Enable debug logging`

## Alternative method

Add the following to configuration.yaml:

```yaml
logger:
  default: warning
  logs:
    custom_components.powercalc: debug
```
