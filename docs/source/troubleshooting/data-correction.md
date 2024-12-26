# Data correction

## Group energy sensor

There might be a sporadic scenario where a group energy sensor spiked to a very high value.
See: [Issue #2836](https://github.com/bramstroker/homeassistant-powercalc/issues/2836)
Exact cause is unknown yet, but here is a way to correct it.

To remedy this, you can correct the energy sensor by following these steps:

1. Find a number (delta) by which we want to reduce the current measurement. It's easy with use of history graph
2. Find the current value of the affected sensor.
3. Call `Powercalc: Calibrate energy sensor` action (service) with the value being a result of `current_value - delta`. You can do it in Developer Tools/Actions in HA.
4. using Developer Tools/Statistics in HA, fix 2 points in long-term statistics: the 1st when the sensor went high, and the 2nd when we fixed it. Likely use 0 (zero) value in both places as replacement.

After these steps, the energy sensor long term statistics should be corrected, and energy dashboard should show correct values.

!!! note
    There are still other places in the database where those values are stored. those are the `statistics_short_term` and `states` tables.
    These are used for short term history in HA and are not corrected by this procedure. When you really need to you can modify these using SQL. Make sure to stop HA before doing this to prevent data corruption.

When you also have a secondary time series DB (like influx or PostgreSQL/Timescale), you also need to correct the values there.
Here is an example for TimescaleDB:

```sql
UPDATE ltss
SET state = state::NUMERIC - 55.8
WHERE entity_id = 'sensor.pg_all_lights_energy'
  AND state NOT IN ('unavailable','unknown')
  AND time BETWEEN '2024-12-21 15:42:10.842109+00' AND '2024-12-22 09:58:58.562645+00';
```
