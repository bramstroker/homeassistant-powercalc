# UPS Devices

This recipe demonstrates how to set up virtual power sensors for UPS (Uninterruptible Power Supply) devices. UPS systems typically have different power consumption levels based on their operating mode (charging, discharging, standby) and load level.

## Basic Configuration

For a simple UPS setup where you know the approximate power consumption for different states, you can use the Fixed strategy with a template:

```yaml
powercalc:
  sensors:
    - entity_id: binary_sensor.ups_charging
      name: UPS Power Consumption
      fixed:
        power: >-
          {% if is_state('binary_sensor.ups_charging', 'on') %}
            35  # Power consumption when charging
          {% else %}
            5   # Standby power consumption
          {% endif %}
```

## UPS with Network Interface

For UPS devices with network monitoring capabilities (like those with Network Management Cards), you can use the NUT (Network UPS Tools) integration in Home Assistant and then create virtual power sensors based on the data it provides:

```yaml
# First set up the NUT integration in your configuration.yaml
nut:
  resources:
    - ups.load
    - battery.charge
    - ups.status

# Then create power sensors based on NUT data
powercalc:
  sensors:
    - entity_id: sensor.ups_battery_charge
      name: UPS Power Consumption
      fixed:
        power: >-
          {% set status = states('sensor.ups_status') %}
          {% set load = states('sensor.ups_load') | float %}
          {% set charge = states('sensor.ups_battery_charge') | float %}

          {% if 'OL' in status and 'CHRG' in status %}
            {# Charging mode - power depends on battery level #}
            {% if charge < 20 %}
              50
            {% elif charge < 50 %}
              40
            {% elif charge < 80 %}
              30
            {% else %}
              15
            {% endif %}
          {% elif 'OL' in status %}
            {# Online but not charging - minimal power #}
            5
          {% elif 'OB' in status %}
            {# On battery - efficiency loss based on load #}
            {{ load * 0.5 }}
          {% else %}
            {# Unknown state - assume minimal power #}
            5
          {% endif %}
```

These examples should provide a good starting point for monitoring the power consumption of various UPS devices. Remember to adjust the power values based on your specific UPS model's specifications or measurements.
