# :zap: PowerCalc: Home Assistant Virtual Power Sensors
Custom component to calculate estimated power consumption of lights and other appliances.
Provides easy configuration to get virtual power consumption sensors in Home Assistant for all your devices which don't have a build in power meter.
This component estimates power usage by looking at brightness, hue/saturation and color temperature etc using different strategies. Other devices than lights are supported, you'll need to manually configure those.
Also possibilities are available to easily put all your energy sensors in groups, for example everything in the living room.

![Preview](https://raw.githubusercontent.com/bramstroker/homeassistant-powercalc/master/assets/preview.gif)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/bramski)

## Post installation steps
- Restart HA
- Add the following entry to `configuration.yaml`:
```yaml
powercalc:
```
- Restart HA final time

## Setup power sensors

After restarting power and energy sensors should appear for the lights found in your HA installation which are supported by powercalc.
Please see the list of [supported models](https://library.powercalc.nl).
When no power sensor is appearing please check the logs for any errors.
Powercalc also provides extensive configuation to setup your own power sensors using different strategies. Please see the main [Documentation](https://github.com/bramstroker/homeassistant-powercalc/blob/master/README.md) on github for all the options and examples.
Also see the [WiKi](https://github.com/bramstroker/homeassistant-powercalc/wiki) for even more information and the FAQ

## Debug logging

Add the following to configuration.yaml:

```yaml
logger:
  default: warning
  logs:
    custom_components.powercalc: debug
```
