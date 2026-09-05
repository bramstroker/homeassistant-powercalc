import {
  enabledParameters,
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
  let entities = field.all_entities
    ? [...(state.deviceEntities["*"] ?? [])]
    : domains.flatMap((domain) => (domain === "light" ? state.lights : state.deviceEntities[domain] ?? []));
  if (field.all_entities && domains.length) {
    entities = entities.filter((entity) => entity.domain && domains.includes(entity.domain));
  }
  if (field.entity_device_classes?.length) {
    entities = entities.filter((entity) => matchesDeviceClass(entity, field.entity_device_classes ?? []));
  }
  const related = relatedEntity(field, state);
  if (!related?.device_id) return field.same_device_only ? [] : entities;
  if (field.same_device_only) return entities.filter((entity) => entity.device_id === related.device_id);
  return entities.sort(
    (left, right) => Number(right.device_id === related.device_id) - Number(left.device_id === related.device_id),
  );
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

export function entityRows(field: FormField, state: FieldState): string[] {
  const chosen = state.selectedEntities[field.name];
  if (chosen) return chosen;
  const stored = state.request && requestFieldValue(state.request, field);
  if (Array.isArray(stored)) return stored.map(String);
  return typeof stored === "string" && stored ? [stored] : [];
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

/** Return the recorder export filename implied by the selected purpose. */
export function recorderExportFilename(purpose: string | undefined, name: string): string {
  const wanted = purpose === "complex_profile" ? "jsonl" : "csv";
  if (!name) return `record.${wanted}`;
  const dot = name.lastIndexOf(".");
  const current = dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
  if (current !== "csv" && current !== "jsonl") return name;
  return current === wanted ? name : `${name.slice(0, dot)}.${wanted}`;
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
