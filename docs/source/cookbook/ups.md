# UPS Devices

This recipe demonstrates how to set up virtual power sensors for UPS (Uninterruptible Power Supply) devices. UPS systems typically have different power consumption levels based on their operating mode (charging, discharging, standby) and load level.

## Basic Configuration

For a simple UPS setup where you know the approximate power consumption for different states, you can use the [fixed strategy](../strategies/fixed.md) with a template:

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

For UPS devices with network monitoring capabilities (like those with Network Management Cards), you can use the [NUT (Network UPS Tools) integration](https://www.home-assistant.io/integrations/nut/) in Home Assistant and then create virtual power sensors based on the data it provides:

Change the `rated_w` and `idle_w` values to match your UPS specifications.
To measure `idle_w`, you can use a power meter to measure the UPS power consumption when it is online but not supplying any load.

```yaml
powercalc:
  sensors:
    - entity_id: sensor.ups_battery_charge
      name: UPS Power Consumption
      fixed:
        power: >-
          {# --- Inputs --- #}
          {% set status = states('sensor.ups_status_data') | upper %}
          {% set load_pct = states('sensor.ups_load') | float(0) %}
          {% set soc = states('sensor.ups_battery_charge') | float(0) %}

          {% set rated_w = 500.0 %}  {# CHANGE ME #}
          {# Idle overhead while online (W). Many small UPSes burn 3–10W just being on. #}
          {% set idle_w = 6.0 %}   {# CHANGE ME #}

          {# Convert % load to output watts supplied by UPS #}
          {% set load_w = (load_pct / 100.0) * rated_w %}

          {# Rough efficiency model (worse at very low load) #}
          {% set eff =
             0.85 if load_pct < 10 else
             0.90 if load_pct < 20 else
             0.93 if load_pct < 40 else
             0.95 if load_pct < 60 else
             0.96 if load_pct < 80 else
             0.97
          %}

          {# Extra charge power when charging (very rough): higher when SoC is low #}
          {% set charge_w =
             35.0 if 'CHRG' in status and soc < 50 else
             20.0 if 'CHRG' in status and soc < 80 else
             8.0  if 'CHRG' in status
             else 0.0
          %}

          {% if 'OB' in status %}
            0
          {% elif 'OL' in status %}
            {{ (load_w / eff) + idle_w + charge_w }}
          {% elif 'BYPASS' in status %}
            {# Bypass usually means raw mains to load; input ~= load + tiny overhead #}
            {{ load_w + 2.0 }}
          {% else %}
            {{ 'unavailable' }}
          {% endif %}
```

These examples should provide a good starting point for monitoring the power consumption of various UPS devices. Remember to adjust the power values based on your specific UPS model's specifications or measurements.
