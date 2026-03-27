# Why is the power of my group sensor too high or lagging?

### Lagging behind
Group power sensors are throttled by default to avoid overwhelming your system with too many state updates. Since a group sensor listens to all underlying power sensor changes, it would otherwise trigger a new state update for every single change, which could impact stability.

By default, updates are limited to once every 2 seconds. This throttling might cause the group sensor to lag slightly behind the actual total of its members at any given moment.

More details on how to configure this can be found here: [Update frequency](../../configuration/update-frequency.md)

### Group total too high
If you feel the group total is too high and doesn't match what you expect, follow these troubleshooting steps:

- Use the action [get_group_entities](../../actions/get-group-entities.md) to verify that all expected member sensors are correctly registered in the group. Might be because of a misconfiguration too many sensors are included in the group.
- To dig deeper, you can [enable debug logging](../debug-logging.md) and look for log lines like: `Group sensor ... State change for ..`. These logs show whenever a member sensor updates and what the new value is. Powercalc keeps track of the latest values internally and calculates the total, then pushes its own state to Home Assistant at the configured interval.
