# Adding Yeelights to Powercalc
Presently, Home Assistant (and the underlying python-yeelight library) does not autodetect the specific model of some Yeelight devices, when adding them via the UI. They may detect the general type (such as *'color'*), but not the generation (like *'color2'*, or actual model number). This prevents us from configuring these devices automatically. To work around this, you must configure those lights manually in some way.

If you know how to find your Yeelights' IP addresses, you can do this with Home Assistant directly:

1. Remove the affected lights from the UI (on the Integrations page)
2. Re-add them to your YAML configuration, according to the [format shown here](https://www.home-assistant.io/integrations/yeelight/#full-configuration), making sure to add the `model` option
3. Restart Home Assistant and confirm working
4. (Optional) Remove them from your YAML configuration. If working, they should now persist in Home Assistant after restarts, with correct model retained

You can alternatively configure each of them manually with Powercalc, specifying `manufacturer` and `model` options.