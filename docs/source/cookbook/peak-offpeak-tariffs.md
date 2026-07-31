# Peak and off-peak energy tariffs

Powercalc does not yet have native fields for separate fixed `peak` and `offpeak`
prices. You can provide the same behavior with a Home Assistant template sensor that
reports the price for the tariff which is currently active. Powercalc then uses that
template sensor as its dynamic energy price.

## Price based on a weekly schedule

First create a [Schedule helper](https://www.home-assistant.io/integrations/schedule/)
named `Peak tariff` under **Settings > Devices & services > Helpers**. Add time blocks
for all periods in which the peak price applies. The resulting
`schedule.peak_tariff` entity is `on` during those blocks and `off` outside them.

Next, add this [template sensor](https://www.home-assistant.io/integrations/template/)
to `configuration.yaml`, replacing the example prices and currency with your own:

```yaml
template:
  - sensor:
      - name: Current energy price
        unique_id: current_energy_price
        unit_of_measurement: "EUR/kWh"
        state: >
          {{ 0.25043 if is_state('schedule.peak_tariff', 'on') else 0.24828 }}
```

The template sensor updates automatically when the schedule changes state; no
automation is needed. After reloading the Template integration or restarting Home
Assistant, configure the new sensor as Powercalc's price sensor:

```yaml
powercalc:
  energy_price_sensor: sensor.current_energy_price
  create_cost_sensors: true
```

When using the GUI, select `sensor.current_energy_price` under **Cost options > Energy
price sensor** instead.

## Price based on an existing tariff indicator

Some meters or integrations already expose the currently active tariff. When you also
have separate price sensors for both tariffs, combine them into one current-price
sensor. For example, if state `2` means peak tariff:

```yaml
template:
  - sensor:
      - name: Current energy price
        unique_id: current_energy_price
        unit_of_measurement: "EUR/kWh"
        availability: >
          {{ is_number(states('sensor.peak_energy_price'))
             and is_number(states('sensor.offpeak_energy_price')) }}
        state: >
          {% if is_state('sensor.current_tariff', '2') %}
            {{ states('sensor.peak_energy_price') }}
          {% else %}
            {{ states('sensor.offpeak_energy_price') }}
          {% endif %}
```

Replace the entity ids and tariff state with those used by your integration, then
configure `sensor.current_energy_price` in Powercalc as shown above.

Whenever the template sensor changes price, Powercalc first charges the energy
consumed up to that moment at the previous price. Energy consumed afterwards is
charged at the new price, so the accumulated cost remains correct across tariff
changes.
