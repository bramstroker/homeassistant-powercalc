import { isMeasurementRequest } from "../../api-decoders";
import { formText } from "../../utils/form";
import {
  buildMeasurementRequest,
  entityDomain,
  entityDomains,
  narrowingField,
} from "../../measurement/definition";
import { meterFor } from "../../power-meter/registry";
import type {
  Capabilities,
  DummyLoadCalibration,
  DummyLoadSpec,
  EntityDescriptor,
  MeasureDefinition,
  MeasurementRequest,
  PowerMeterSpec,
} from "../../types";

interface RequestOptions {
  definition: MeasureDefinition;
  form: FormData;
  capabilities: Capabilities;
  meter: PowerMeterSpec;
  measureDevice: string;
  dummyController: boolean;
  calibration: DummyLoadCalibration | null;
  initialRequest?: MeasurementRequest;
  entities: EntityDescriptor[];
  entityErrors: Readonly<Record<string, string>>;
}

export type RequestResult = { request: MeasurementRequest; error?: never } | { request?: never; error: string };

/** Validate and assemble the complete request represented by the setup form. */
export function prepareRequest(options: RequestOptions): RequestResult {
  const { definition, form } = options;
  const failedDomain = options.dummyController
    ? undefined
    : entityDomains(definition, form).find((domain) => options.entityErrors[domain]);
  if (failedDomain) return { error: `Could not load ${failedDomain} entities. Retry before starting the measurement.` };

  const empty = definition.fields.find(
    (field) => field.control === "multi_select" && field.required && form.getAll(field.name).length === 0,
  );
  if (empty) return { error: `Select at least one ${empty.label.toLowerCase().replace(/s$/, "")}.` };

  let request: MeasurementRequest;
  try {
    request = buildMeasurementRequest(
      definition,
      form,
      options.capabilities,
      options.meter,
      options.measureDevice,
      options.dummyController,
    );
  } catch (error) {
    return { error: error instanceof Error ? error.message : "The measurement form produced an invalid request." };
  }
  const defaults = profileDefaults(options);
  const previous = previousRequest(options.initialRequest, definition, request);
  request.model_id ||= previous?.model_id || defaults.model_id;
  request.product_name ||= previous?.product_name || defaults.product_name;
  request.session_name ||= previous?.session_name || defaults.session_name || definition.label;
  request.dummy_load = meterFor(options.meter.type).supportsDummyLoad
    ? dummyLoadSpec(form, options.calibration)
    : undefined;

  const mismatch = options.dummyController ? undefined : narrowedEntityMismatch(definition, form);
  if (mismatch) return { error: mismatch };
  if (!isMeasurementRequest(request)) return { error: "The measurement form produced an invalid request." };
  return { request };
}

/** Only metadata shared by every selected device is safe as a profile default. */
function profileDefaults(options: RequestOptions): { model_id: string; product_name: string; session_name: string } {
  const empty = { model_id: "", product_name: "", session_name: "" };
  if (options.dummyController) return empty;
  const controller = options.definition.fields.find((field) => field.role === "controller");
  if (!controller) return empty;
  const ids = options.form.getAll(controller.name).map(String).filter(Boolean);
  const selected = ids.map((id) => options.entities.find((entity) => entity.entity_id === id));
  const shared = (field: "model_id" | "product_name") => {
    const values = new Set(selected.map((entity) => entity?.[field]));
    return values.size === 1 ? [...values][0] ?? "" : "";
  };
  const modelId = shared("model_id");
  return {
    // An HA model ID can contain characters not allowed in an export path.
    model_id: modelId.length <= 120 && /^[A-Za-z0-9][A-Za-z0-9 ._()+-]*$/.test(modelId) ? modelId : "",
    product_name: shared("product_name"),
    session_name: selected.map((entity, index) => entity?.name || ids[index]).join(", ").slice(0, 200),
  };
}

function previousRequest(
  initial: MeasurementRequest | undefined,
  definition: MeasureDefinition,
  request: MeasurementRequest,
): MeasurementRequest | undefined {
  if (initial?.measure_type !== definition.measure_type) return undefined;
  if (JSON.stringify(initial.controller) !== JSON.stringify(request.controller)) return undefined;
  return initial;
}

/** Reject a controller left behind after its narrowing selection changed. */
function narrowedEntityMismatch(definition: MeasureDefinition, form: FormData): string | undefined {
  for (const field of definition.fields) {
    const source = narrowingField(definition, field);
    if (!source || field.role !== "controller") continue;
    const expected = entityDomain(definition, field, formText(form, source.name));
    const chosen = formText(form, field.name);
    if (!expected || !chosen.startsWith(`${expected}.`)) {
      return `Select a ${expected ?? "matching"} entity for the chosen ${source.label.toLowerCase()}.`;
    }
  }
  return undefined;
}

/** What the submitted form means for this measurement, or undefined when the load is not used. */
function dummyLoadSpec(form: FormData, calibration: DummyLoadCalibration | null): DummyLoadSpec | undefined {
  if (!form.has("use_dummy_load")) return undefined;
  if (form.get("dummy_load_mode") === "reuse" && calibration) {
    return { mode: "reuse", description: calibration.description, resistance: calibration.resistance };
  }
  return { mode: "calibrate", description: formText(form, "dummy_load_description") };
}
