# My light is in the supported model list but not discovered. What can I do?

Powercalc scans your HA installation for all devices having a manufacturer and model information.
It tries to match this information against the model_id and aliases shown in the [supported models](https://library.powercalc.nl) list.
Some integrations return different product codes / model id's for the same light which may cause a mismatch. For example Hue and Zigbee2Mqtt.
To have a look at which model was discovered by powercalc you can enable debug logging.
Now look for the lines `Auto discovered model (manufacturer=xx, model=xx)` in the logs, and see if the model id matches.
When it does not match something powercalc known an aliases might be added. You can create an issue for that or better yet provide a Pull Request for the changes.
