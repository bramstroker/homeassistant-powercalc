# Cost sensors

Powercalc can create **cost sensors** which track how much the consumed energy costs.
A cost sensor multiplies the energy consumed by an energy price and accumulates the
result over time. The created sensor has device class `monetary` and uses your Home
Assistant currency as unit of measurement, so it can be used on dashboards and in the
[energy dashboard](https://www.home-assistant.io/docs/energy/).

The energy price is configured **globally**, either as a fixed price or by pointing to a
sensor which provides the current price per kWh (for example a dynamic tariff
integration such as Nordpool, Tibber or Frank Energie).

## Configuring the energy price

Define the price once in the global configuration. Provide **either** a fixed price
**or** a price sensor.

Fixed price (per kWh, in your local currency):

```yaml
powercalc:
  energy_price: 0.25
```

Price from an existing sensor:

```yaml
powercalc:
  energy_price_sensor: sensor.current_energy_price
```

When both are set, the fixed price is ignored and the price sensor is used.

## Enabling cost sensors

Similar to energy sensors and utility meters, cost sensor creation can be toggled
globally and per powercalc sensor.

To create cost sensors for **all** powercalc sensors:

```yaml
powercalc:
  energy_price: 0.25
  create_cost_sensors: true
```

To enable/disable per sensor (this overrides the global setting for that sensor):

```yaml
sensor:
  - platform: powercalc
    entity_id: light.floorlamp_livingroom
    create_cost_sensor: true
```

Toggling cost sensor creation can also be done when creating sensors with the GUI, both
in the global configuration and on a per sensor basis.

!!! note

    A cost sensor is derived from the energy sensor, so an energy sensor must be created
    as well. Assume you have a light `light.floorlamp_livingroom`, then you would get:

    - `sensor.floorlamp_livingroom_power`
    - `sensor.floorlamp_livingroom_energy`
    - `sensor.floorlamp_livingroom_cost`

## How the cost is calculated

The cost sensor reacts to changes of the energy sensor. On every update it takes the
amount of energy consumed since the previous update and multiplies it by the price that
is valid **at that moment**. When you use a dynamic price sensor, a price change settles
the energy consumed up to that point at the **previous** price before the new price takes
effect. This way energy is always priced against the tariff that was active while it was
consumed, and the accumulated cost stays correct even when the price changes over time.

## Limitations / tariffs

Fixed per-tariff prices (for example a different fixed `peak` and `offpeak` price used
together with utility meter [tariffs](utility-meter.md#tariffs)) are **not** supported
yet. If your utility uses different tariffs throughout the day, use a price sensor that
already reflects the currently active tariff price — the accumulate-at-consumption
behavior then yields the correct multi-tariff cost without any extra configuration.
Native support for fixed per-tariff prices is planned for a future release.
