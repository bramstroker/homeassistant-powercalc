import {
  enabledParameters,
  entityDomainsForOption,
  fieldOptions,
  fieldVisible,
  requestFieldValue,
} from "../../measurement/definition";
import type {
  EntityDescriptor,
  FormField,
  FormFieldOption,
  LutMode,
  MeasureDefinition,
  MeasurementRequest,
} from "../../types";

export interface FieldState {
  definition: MeasureDefinition;
  request?: MeasurementRequest;
  lights: EntityDescriptor[];
  deviceEntities: Record<string, EntityDescriptor[]>;
  selectedEntities: Record<string, string[]>;
  selectValues: Record<string, string>;
  multiSelection: Record<string, string[]>;
  dummyController: boolean;
}

type EntitySelectionState = Pick<FieldState, "selectedEntities" | "request">;

export function visible(field: FormField, state: FieldState): boolean {
  return fieldVisible(field, (name) => {
    const source = state.definition.fields.find((candidate) => candidate.name === name);
    if (!source) return "";
    if (source.control === "select") return selectValue(source, state) ?? "";
    const stored = state.request && requestFieldValue(state.request, source);
    return selectedEntityId(source, state) || (typeof stored === "string" ? stored : "");
  });
}

export function entityChoices(
  field: FormField,
  state: FieldState,
  domains = field.entity_domains ?? [],
): EntityDescriptor[] {
  const source = field.narrowed_by
    ? state.definition.fields.find((candidate) => candidate.name === field.narrowed_by)
    : undefined;
  const allowedDomains = source?.control === "select"
    ? entityDomainsForOption(state.definition, field, selectValue(source, state))
    : domains;
  if (field.all_entities && source?.control === "select" && !allowedDomains.length) return [];
  let entities = matchingEntities(field, state, allowedDomains, source);
  const related = relatedEntity(field, state);
  if (state.definition.measure_type === "recorder") {
    entities = filterRecordingEntities(field, state, entities, related);
  }
  if (!related?.device_id) return field.same_device_only ? [] : entities;
  if (field.same_device_only) return entities.filter((entity) => entity.device_id === related.device_id);
  return entities.sort(
    (left, right) => Number(right.device_id === related.device_id) - Number(left.device_id === related.device_id),
  );
}

function matchingEntities(
  field: FormField, state: FieldState, allowedDomains: string[], source?: FormField,
): EntityDescriptor[] {
  let entities = field.all_entities
    ? [...(state.deviceEntities["*"] ?? [])]
    : allowedDomains.flatMap((domain) => (domain === "light" ? state.lights : state.deviceEntities[domain] ?? []));
  entities = entities.filter(hasEnabledLiveState);
  if (field.role === "controller") {
    // Configuration and diagnostic switches (e.g. a Shelly BLE setting) are not relays.
    entities = entities.filter((entity) => entity.entity_category !== "config" && entity.entity_category !== "diagnostic");
  }
  if (field.all_entities && allowedDomains.length) {
    entities = entities.filter((entity) => entity.domain && allowedDomains.includes(entity.domain));
  }
  if (field.entity_device_classes?.length) {
    entities = entities.filter((entity) => matchesDeviceClass(entity, field.entity_device_classes ?? []));
  }
  if (field.name === "primary_entity_id" && source && selectValue(source, state) === "printer") {
    entities = entities.filter((entity) => !entity.unit);
  }
  return entities;
}

function filterRecordingEntities(
  field: FormField, state: FieldState, entities: EntityDescriptor[], related?: EntityDescriptor,
): EntityDescriptor[] {
  const tracking = field.name === "tracked_entity_ids";
  if (!tracking && field.name !== "additional_entity_ids") return entities;
  if (!related?.device_id) return [];
  const allowedDevices = new Set([related.device_id, ...(related.related_device_ids ?? [])]);
  const relatedEntities = entities.filter((entity) => entity.entity_id !== related.entity_id
    && allowedDevices.has(entity.device_id ?? ""));
  if (tracking) return relatedEntities.filter((entity) => entity.integration !== "powercalc");
  const batteryId = findRecordingBatteryId(state);
  return relatedEntities.filter((entity) => entity.entity_id !== batteryId);
}

function findRecordingBatteryId(state: FieldState): string {
  const batteryField = state.definition.fields.find((candidate) => candidate.name === "battery_entity_id");
  if (!batteryField) return "";
  const selected = selectedEntityId(batteryField, state);
  if (selected) return selected;
  const batteries = entityChoices(batteryField, state);
  return batteries.length === 1 ? batteries[0]!.entity_id : "";
}

export function availableOptions(field: FormField, state: FieldState): FormFieldOption[] {
  return state.dummyController ? field.options : fieldOptions(field, narrowedModes(field, state));
}

export function selectedOptions(field: FormField, state: FieldState): string[] {
  const available = availableOptions(field, state).map((option) => option.value);
  const stored = state.request && requestFieldValue(state.request, field);
  const chosen = state.multiSelection[field.name] ?? (Array.isArray(stored) && stored.length ? stored : available);
  return available.filter((value) => chosen.includes(value));
}

export function activeParameters(state: FieldState): ReadonlySet<string> {
  const active = new Set<string>();
  for (const field of state.definition.fields.filter((candidate) => candidate.control === "multi_select")) {
    for (const name of enabledParameters(field, selectedOptions(field, state))) active.add(name);
  }
  return active;
}

/** Keep empty rows: an unanswered select is still a row in the form. */
export function entityRows(field: FormField, state: EntitySelectionState): string[] {
  const chosen = state.selectedEntities[field.name];
  if (chosen !== undefined) return chosen;
  const stored = state.request && requestFieldValue(state.request, field);
  if (Array.isArray(stored)) return stored.map(String);
  return typeof stored === "string" && stored ? [stored] : [];
}

function hasEnabledLiveState(entity: EntityDescriptor): boolean {
  return !entity.disabled_by && entity.has_live_state !== false;
}

export function disabledVacuumEntityIds(state: FieldState): string[] {
  const vacuumField = state.definition.fields.find((field) => field.name === "vacuum_entity_id");
  if (!vacuumField) return [];
  const entities = state.deviceEntities["*"] ?? [];
  const vacuumId = selectedEntityId(vacuumField, state);
  return entities.find((entity) => entity.entity_id === vacuumId)?.disabled_recording_entity_ids ?? [];
}

export function selectedEntityId(field: FormField, state: FieldState): string {
  return entityRows(field, state)[0] ?? "";
}

export function selectedEntityIds(field: FormField, state: FieldState): string[] {
  return entityRows(field, state).filter(Boolean);
}

export function selectValue(field: FormField, state: FieldState): string | undefined {
  const stored = state.request && requestFieldValue(state.request, field);
  return state.selectValues[field.name]
    ?? (typeof stored === "string" ? stored : undefined)
    ?? field.options[0]?.value;
}

export function recorderPurpose(state: FieldState): string | undefined {
  if (state.definition.measure_type !== "recorder") return undefined;
  if (state.selectValues.recorder_purpose) return state.selectValues.recorder_purpose;
  if (state.request?.measure_type === "recorder") return state.request.recorder_purpose;
  return state.definition.fields.find((field) => field.name === "recorder_purpose")?.default?.toString();
}

function narrowedModes(field: FormField, state: FieldState): LutMode[] | undefined {
  const source = field.narrowed_by
    ? state.definition.fields.find((candidate) => candidate.name === field.narrowed_by)
    : undefined;
  if (!source) return undefined;
  const choices = entityChoices(source, state);
  const selected = selectedEntityIds(source, state)
    .map((entityId) => choices.find((entity) => entity.entity_id === entityId))
    .filter((entity): entity is EntityDescriptor => Boolean(entity));
  const [first, ...rest] = selected;
  if (!first) return undefined;
  return (first.supported_modes ?? []).filter(
    (mode) => rest.every((entity) => entity.supported_modes?.includes(mode)),
  );
}

function matchesDeviceClass(entity: EntityDescriptor, deviceClasses: readonly string[]): boolean {
  if (!entity.device_class || !deviceClasses.includes(entity.device_class)) return false;
  if (entity.device_class !== "battery") return true;
  return entity.domain === "sensor"
    && entity.unit === "%"
    && !["unavailable", "unknown", "none"].includes((entity.state ?? "").toLowerCase())
    && Number.isFinite(Number(entity.state));
}

function relatedEntity(field: FormField, state: FieldState): EntityDescriptor | undefined {
  if (!field.related_to) return undefined;
  const source = state.definition.fields.find((candidate) => candidate.name === field.related_to);
  if (!source) return undefined;
  const entityId = selectedEntityId(source, state);
  return (state.deviceEntities["*"] ?? []).find((entity) => entity.entity_id === entityId);
}
