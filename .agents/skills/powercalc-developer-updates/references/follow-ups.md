# Deferred upstream improvements

Last assessed: 2026-10-31. These are unresolved follow-ups, not a review cutoff.
Reassess against the current checkout and support window; remove entries once
implemented or no longer relevant, and add newly deferred findings here.

## Conditional flow fields

- [Announcement, 2026-10-21](https://contributors.home-assistant.io/blog/2026/10/21/form-fields-visible/)
- Available in HA 2026.11. Optional UI improvement; deferred to avoid adding
  compatibility code solely for this feature.
- First use case: show `energy_filter_outlier_max` only while
  `energy_filter_outlier_enabled` is true in
  `custom_components/powercalc/flow_helper/schema.py`.
- Revisit when HA 2027.3 is stable: 2026.11 is then the oldest of the five most
  recent monthly releases. Also check the checkout's advertised minimum.
- Verify that schema default filling preserves visibility metadata and that
  disabling the filter handles previously saved values correctly. HA discards
  hidden field values, so this affects submission semantics as well as display.

## In-place entity ID changes

- [Announcement, 2026-10-12](https://contributors.home-assistant.io/blog/2026/10/12/new-entity-lifecycle-hooks/)
- HA 2026.11 adds `async_entity_id_changed`. Custom entities with add/remove
  hooks retain the old remove-and-add behaviour until they opt in. This fallback
  is removed in HA 2027.11, so migration is required before that release.
- Revisit from HA 2027.3, when the hook covers the five-release window, or earlier
  if a rename bug makes migration urgent. Check the advertised minimum too.
- PowerCalc's `BaseEntity` and sensor subclasses implement lifecycle hooks and
  currently do not opt in. Audit the complete class hierarchy before adding a
  hook; call the parent hook and update bookkeeping keyed by the entity's ID.
- Inspect `DATA_ENTITIES` and `DATA_GROUP_ENTITIES` in `sensor.py`, standby power
  bookkeeping in `sensors/power.py`, and `PreviousStateStore` in
  `sensors/group/custom.py`. The latter persists member states under a group
  entity ID. An empty opt-in hook does not migrate that data.
- Test live power, energy, group and utility-meter renames, continued updates,
  preserved totals, and cleanup after removal on the new HA lifecycle.
