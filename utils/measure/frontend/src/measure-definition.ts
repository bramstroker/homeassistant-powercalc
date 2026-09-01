import { formChecked, formList, formNumber, formText } from "./form";
import type {
  BaseMeasurementRequest,
  Capabilities,
  FormField,
  FormFieldOption,
  LutMode,
  MeasureDefinition,
  MeasurementParameters,
  MeasurementRequest,
  PowerMeterSpec,
} from "./types";

/** A single submitted form value, before it is placed in a request. */
type FieldValue = string | number | boolean | string[];

/** Fields the device form renders itself; the power meter has its own dedicated section. */
export function deviceFields(definition: MeasureDefinition): FormField[] {
  return definition.fields.filter((field) => field.role !== "power_meter");
}

/**
 * Value a previous run stored for a form field, so the form can be prefilled.
 * The inverse of the assignment {@link buildMeasurementRequest} performs.
 */
export function requestFieldValue(request: MeasurementRequest, field: FormField): FieldValue | undefined {
  if (field.role === "controller") return controllerEntityId(request);
  const value = (request as unknown as Record<string, unknown>)[field.name];
  return isFieldValue(value) ? value : undefined;
}

function controllerEntityId(request: MeasurementRequest): string | string[] | undefined {
  const { controller } = request as { controller?: { type: string; entity_id?: string; entity_ids?: string[] } };
  if (controller?.type === "hass") return controller.entity_id;
  return controller?.type === "hass_multi" ? controller.entity_ids : undefined;
}

function isFieldValue(value: unknown): value is FieldValue {
  if (Array.isArray(value)) return value.every((entry) => typeof entry === "string");
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

/**
 * Options a field offers right now. A field can declare that a controller entity narrows
 * it, in which case only the options that entity reports as supported are offered.
 */
export function fieldOptions(field: FormField, supportedModes?: LutMode[]): FormFieldOption[] {
  const supported = field.narrowed_by ? supportedModes : undefined;
  if (!supported?.length) return field.options;
  return field.options.filter((option) => supported.includes(option.value as LutMode));
}

/**
 * Every parameter that some option claims. A parameter outside this set always applies;
 * one inside it only applies while the option that claims it is selected.
 */
export function gatedParameters(definition: MeasureDefinition): ReadonlySet<string> {
  return new Set(definition.fields.flatMap((field) => field.options.flatMap((option) => option.enables ?? [])));
}

/** Measurement parameters the currently selected options activate; the rest stay hidden. */
export function enabledParameters(field: FormField, selected: readonly string[]): ReadonlySet<string> {
  return new Set(
    field.options
      .filter((option) => selected.includes(option.value))
      .flatMap((option) => option.enables ?? []),
  );
}

/** The field, if any, whose current value constrains this one. */
export function narrowingField(definition: MeasureDefinition, field: FormField): FormField | undefined {
  return field.narrowed_by ? definition.fields.find((candidate) => candidate.name === field.narrowed_by) : undefined;
}

/** Domain an entity field accepts, taken from the option selected in the field that narrows it. */
export function entityDomain(definition: MeasureDefinition, field: FormField, selectedOption?: string): string | undefined {
  const source = narrowingField(definition, field);
  if (source) return source.options.find((option) => option.value === selectedOption)?.entity_domain ?? undefined;
  return field.entity_domains?.[0];
}

export function entityDomains(definition: MeasureDefinition, values?: FormData): string[] {
  const domains = definition.fields
    .filter((field) => field.role === "controller")
    .flatMap((field) => {
      const source = narrowingField(definition, field);
      if (!source) return field.entity_domains ?? [];
      // Without a submitted value every option is still reachable, so offer all their domains.
      const submitted = values ? formText(values, source.name) : "";
      if (submitted) return [entityDomain(definition, field, submitted)];
      return source.options.map((option) => option.entity_domain);
    })
    // Lights already arrive with the startup catalog, so they are never fetched on demand.
    .filter((domain): domain is string => Boolean(domain) && domain !== "light");
  const visibleValue = (name: string): string => {
    const submitted = values ? formText(values, name) : "";
    if (submitted) return submitted;
    const field = definition.fields.find((candidate) => candidate.name === name);
    return String(field?.default ?? field?.options[0]?.value ?? "");
  };
  if (definition.fields.some((field) => field.all_entities && fieldVisible(field, visibleValue))) domains.push("*");
  return domains;
}

/**
 * A stored request seen as submitted form values, so domain resolution reads the values it
 * was started with. Without this a restored request resolves against field defaults, and a
 * field only its own purpose makes visible never has its entities fetched.
 */
export function requestFormData(definition: MeasureDefinition, request: MeasurementRequest): FormData {
  const values = new FormData();
  for (const field of definition.fields) {
    const value = requestFieldValue(request, field);
    if (value === undefined || value === "") continue;
    for (const item of Array.isArray(value) ? value : [value]) values.append(field.name, String(item));
  }
  return values;
}

/** Whether the server-declared dependencies currently make a field relevant. */
export function fieldVisible(field: FormField, value: (name: string) => string): boolean {
  return Object.entries(field.visible_when ?? {}).every(([name, accepted]) => accepted.includes(value(name)));
}

/**
 * Build a request purely from what the server declared about the measure type.
 *
 * Every field carries a role: the controller field becomes the discriminated controller
 * spec, the power meter comes from the client's own configuration, and every other field
 * sets the request attribute of the same name. Adding a measure type therefore needs no
 * change here — only a registry entry server-side.
 */
export function buildMeasurementRequest(
  definition: MeasureDefinition,
  form: FormData,
  capabilities: Capabilities,
  powerMeter: PowerMeterSpec,
  measureDevice: string,
  dummyController = false,
): MeasurementRequest {
  const base: BaseMeasurementRequest = {
    model_id: formText(form, "model_id") || "measurement",
    product_name: formText(form, "product_name") || definition.label,
    measure_device: measureDevice,
    power_meter: powerMeter,
    generate_model: definition.supports_profile,
    parameters: submittedParameters(definition, form, capabilities),
    // Only a resumable type offers the choice; the rest fall through to a fresh session.
    resume_policy: (formText(form, "resume_policy") || "new") as BaseMeasurementRequest["resume_policy"],
  };

  const declared: Record<string, unknown> = {};
  for (const field of definition.fields) {
    if (field.role === "power_meter") continue;
    if (!fieldVisible(field, (name) => formText(form, name))) continue;
    if (field.role === "controller") {
      declared.controller = controllerSpec(form, field, dummyController);
      continue;
    }
    declared[field.name] = formValue(form, field);
  }

  // The server validates the assembled payload against its own discriminated model.
  return { ...base, ...declared, measure_type: definition.measure_type } as MeasurementRequest;
}

/** The controller spec a submitted entity field describes: a virtual device, one entity, or several. */
function controllerSpec(form: FormData, field: FormField, dummyController: boolean): Record<string, unknown> {
  if (dummyController) return { type: "dummy" };
  const entityIds = form.getAll(field.name)
    .filter((value): value is string => typeof value === "string")
    .map((value) => value.trim())
    .filter(Boolean);
  if (entityIds.length > 1) return { type: "hass_multi", entity_ids: entityIds };
  return { type: "hass", entity_id: entityIds[0] ?? "" };
}

/** The tuning parameters this type declares, taken from the form where the user set one. */
function submittedParameters(definition: MeasureDefinition, form: FormData, capabilities: Capabilities): MeasurementParameters {
  const parameters: Record<string, number> = { ...capabilities.defaults };
  for (const { name } of definition.parameters) {
    const value = form.get(name);
    if (typeof value === "string" && value !== "") parameters[name] = Number(value);
  }
  return parameters as unknown as MeasurementParameters;
}

/** Read one submitted field, coerced to the type its declared control produces. */
function formValue(form: FormData, field: FormField): FieldValue {
  if (field.control === "boolean") return formChecked(form, field.name);
  if (field.control === "multi_select" || (field.control === "entity" && field.multiple)) {
    return formList(form, field.name).filter(Boolean);
  }
  return field.control === "number" ? formNumber(form, field.name) : formText(form, field.name);
}
