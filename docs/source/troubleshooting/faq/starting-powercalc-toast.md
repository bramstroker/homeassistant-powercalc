# Why does Home Assistant say "Starting Powercalc" during startup?

While Home Assistant boots, the frontend shows a toast at the bottom of the screen:

> Starting Powercalc. Not everything will be available until startup is finished.

Powercalc is often the integration named there, sometimes for ten seconds or more. This does **not** mean Powercalc is slow, and it does not mean Powercalc is holding up your startup.

## What the message actually means

Home Assistant shows this toast for a single integration at a time: the one with the highest number in its live startup feed. That number is not the time an integration spent working, it is the sum of the elapsed time of every config entry it currently has in setup.

Powercalc typically has far more config entries than other integrations, one per configured power sensor. An installation with 60 sensors has 60 config entries being set up at the same time, and all 60 are added together. So Powercalc reaches the top of that list even when every individual entry finishes almost instantly, and it stays there until Home Assistant has finished booting.

An integration with a single config entry that genuinely takes 5 seconds reports `5`. Powercalc with 60 entries that each take a fraction of a second can report a much larger number while doing far less work.

## Checking the real startup time

Home Assistant logs the actual figure at `INFO` level. Add this to `configuration.yaml`, restart, and search the log for `Setup of domain powercalc`:

```yaml
logger:
  default: info
```

```
Setup of domain powercalc took 0.06 seconds
```

That is the number that matters. On a typical installation Powercalc sets up in well under a second, and its device discovery runs 10 seconds after startup, deliberately out of the way of the boot process.

To see which integrations really do dominate your startup, sort all the `Setup of domain ... took ... seconds` lines in the same log.

## Why it can still take a while before sensors appear

Two things happen after Powercalc itself is set up:

- Home Assistant sets up integrations in parallel during startup. Powercalc's config entries wait their turn in that queue, which on a large installation can be several seconds. Powercalc is idle during this time.
- Group sensors and `include` based sensors are created only once Home Assistant fires its "started" event, because they need all of their member entities to exist first. That event fires at the very end of startup by definition.

Both are expected, and neither indicates a problem.

## When to investigate further

If `Setup of domain powercalc took ...` reports more than a couple of seconds, something is genuinely wrong. [Enable debug logging](../debug-logging.md) for Powercalc and look for repeated profile downloads or errors while loading the library, then report it on GitHub with that log.
