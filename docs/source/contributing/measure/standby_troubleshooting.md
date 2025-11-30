## 🔧 Standby Power Shows as 0W

Some bulbs use **very little standby power** (often 0.1–0.3 W). Many smart plugs cannot accurately measure loads this small, causing the measurement tool to report **0W**.

### Why This Happens
Most consumer grade smart plugs have a minimum measurable load of **0.3–0.5 W**. Anything below that is rounded down to zero, even though the bulb *does* consume standby power.

### ✔️ Troubleshooting Steps

#### 1. Measure Multiple Bulbs in Parallel
If you have more than one identical bulb, connect them **in parallel** and measure their combined standby power.

Example:

- Expected standby: ~0.2 W per bulb
- With 4 bulbs: ~0.8 W total → usually measurable

Make sure to have a group in HA that turns on/off all bulbs simultaneously during measurement.
In the measure tool wizard select `yes` when asked `Are you measuring multiple lights?`.
On the next screen, enter the number of bulbs you are measuring.

#### 2. Add a Dummy Load
Some smart plugs require a **stable resistive load** before they can measure accurately.
Use a small **incandescent bulb** (e.g., 25–40 W) as a dummy load on the same circuit.
An oven bulb is a good choice since it uses little power and is easy to find.

!!! warning

    Do **not** use an LED bulb as a dummy load.
    LED bulbs are not stable resistive loads and will cause fluctuating or inaccurate readings.

#### 3. Try a Different Smart Plug / Energy Meter
Not all smart meters can measure sub-watt loads. If possible, try another brand or model known for decent low-load accuracy.

Examples:

- Good: many Tasmota-based plugs, Shelly Plug Gen3, Blitzwolf/Nous plugs
- Less accurate: older Shelly Plug S, many Tuya-based plugs below 0.5 W

#### 4. Standby Is Too Low to Measure
If none of the above methods help, the bulb’s standby consumption is likely **below the accuracy threshold** of your meter.
In that case the measurement tool cannot determine a reliable value.

You may manually set a fallback estimate (e.g., 0.2 W), but actual measurement is always preferred when possible.
When doing this please note this in the PR description when submitting your measurements.
