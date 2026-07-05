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

You can also add a fixed per-kWh surcharge to either price source. This is useful for
taxes, grid fees, provider markup, or other usage-based charges that should be added
to the base energy price:

```yaml
powercalc:
  energy_price: 0.25
  energy_price_surcharge: 0.05
```

With this configuration, each consumed kWh is charged at `0.30` in your Home Assistant
currency.

For percentage-based taxes or fees, use `energy_price_multiplier`. For example, use
`1.21` to add 21% tax:

```yaml
powercalc:
  energy_price: 0.25
  energy_price_surcharge: 0.05
  energy_price_multiplier: 1.21
```

The effective price is calculated as:

```text
(energy_price or energy_price_sensor + energy_price_surcharge) * energy_price_multiplier
```

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

    Toggling `create_cost_sensors` in the global GUI configuration does not automatically
    change the per-sensor toggle for sensors you already created through the GUI.
    Therefore, whenever you flip this toggle (on or off), an extra step is shown that lets
    you enable the **Apply to existing sensors** option. When enabled, every existing GUI
    powercalc sensor is updated to match the new setting.

## Naming

By default a cost sensor is named `{appliance} cost` (for example `Floorlamp cost`). You
can change this globally with `cost_sensor_naming`, similar to `energy_sensor_naming` and
`power_sensor_naming`. Use the `{}` placeholder for the name of your appliance. This also
changes the entity id of the sensor.

```yaml
powercalc:
  energy_price: 0.25
  cost_sensor_naming: "{} energy costs"
```

To only change the friendly name (and keep the entity id), use
`cost_sensor_friendly_naming`:

```yaml
powercalc:
  energy_price: 0.25
  cost_sensor_friendly_naming: "Costs of {}"
```

Both settings can also be configured in the GUI under the cost options step of the global
configuration.

!!! note

    A cost sensor is derived from the energy sensor, so an energy sensor must be created
    as well. Assume you have a light `light.floorlamp_livingroom`, then you would get:

    - `sensor.floorlamp_livingroom_power`
    - `sensor.floorlamp_livingroom_energy`
    - `sensor.floorlamp_livingroom_cost`

## Cost per utility meter

When you also enable [utility meters](utility-meter.md), Powercalc creates an additional
cost sensor for **every** utility meter, next to the cost sensor for the energy sensor.
This lets you track the cost per cycle (daily, weekly, monthly, ...) just like the energy
utility meters track consumption per cycle.

For example, with `create_cost_sensors`, `create_utility_meters` and a `daily` and
`monthly` meter enabled, a light `light.floorlamp_livingroom` would get:

- `sensor.floorlamp_livingroom_cost` (total cost)
- `sensor.floorlamp_livingroom_energy_daily_cost`
- `sensor.floorlamp_livingroom_energy_monthly_cost`

The per-meter cost sensors reset together with their utility meter, so they always
reflect the cost accumulated during the current cycle. They are only created when both
cost sensors and utility meters are enabled.

## How the cost is calculated

The cost sensor reacts to changes of the energy sensor. On every update it takes the
amount of energy consumed since the previous update and multiplies it by the price that
is valid **at that moment**. When `energy_price_surcharge` is configured, it is added to
the fixed price or dynamic price sensor value. When `energy_price_multiplier` is
configured, it is applied after the surcharge. When you use a dynamic price sensor, a
price change settles the energy consumed up to that point at the **previous** price
before the new price takes effect. This way energy is always priced against the tariff
that was active while it was consumed, and the accumulated cost stays correct even when
the price changes over time.

## Limitations / tariffs

Fixed per-tariff prices (for example a different fixed `peak` and `offpeak` price used
together with utility meter [tariffs](utility-meter.md#tariffs)) are **not** supported
yet. If your utility uses different tariffs throughout the day, use a price sensor that
already reflects the currently active tariff price — the accumulate-at-consumption
behavior then yields the correct multi-tariff cost without any extra configuration.
Native support for fixed per-tariff prices is planned for a future release.
