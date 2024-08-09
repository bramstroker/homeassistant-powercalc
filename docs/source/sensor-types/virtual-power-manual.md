# Virtual power sensor (manual)

To manually add virtual power sensors for your devices you can use the GUI or add some configuration to `configuration.yaml`.

Powercalc offers various calculation strategies that can be used to establish a new virtual power sensor. Each method is suitable for specific use cases. To learn about all options please see [strategies](../strategies/index.md).

## GUI

You can create new virtual power sensors with the GUI.

Just click the button to directly add a powercalc sensor:

[![config_flow_start](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=powercalc)

When this is not working.

- Go to `Settings` -> `Devices & Services`
- Click `Add integration`
- Search and click `Powercalc`

Select `Virtual power (manual)` and follow the instructions.

After you have walked through the wizard the new powercalc sensor must be created and appear in the list.
When you click on it you can see the entities which are created.
Some options can be changed afterwards, just click `Configure`

!!! important

    You can omit source entity when you want to setup a calculation based on for example a template. In this case you MUST provide a name thought.
    So either source entity or name are mandatory to setup a virtual power sensor.

## YAML

To create a power sensor with YAML you'll have to add a new entry under `powercalc->sensors` line in `configuration.yaml`.

Most basic example:

```yaml
powercalc:
  sensors:
    - entity_id: light.my_light
      fixed:
        power: 20
```

For all the possible options see the strategy sections as linked above, [sensor configuration](../configuration/sensor-configuration.md) and the rest of the Powercalc documentation.

Adding a sensor using the YAML method will not add the Powercalc integration page. Only entities created with the GUI will appear there.
The sensor will functionally be the same, and you can find it in the global entities list.

!!! important

    After changing the configuration you'll need to restart HA to get your power sensors to appear.

### Splitting up configuration

Alternatively you could move all powercalc configuration and sensors to a separate YAML file to prevent getting one massive `configuration.yaml` and keep things maintainable.
To do so add the following line to `configuration.yaml`:

```yaml
powercalc: !include includes/powercalc.yaml
```

Now in `powercalc.yaml` add all the global configuration and sensors. You need to omit `powercalc:` in this case.

```yaml
sensors:
  - entity_id: light.my_light
    fixed:
      power: 20
  - entity_id: light.my_light2
    fixed:
      power: 40
```

A third way would be to use the [packages](https://www.home-assistant.io/docs/configuration/packages/) system which Home Assistant provides.
