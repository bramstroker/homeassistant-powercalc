import { requestFieldValue } from "../../measurement/definition";
import { summarize } from "../../power-meter/registry";
import type { FormField, MeasureDefinition, MeasurementRequest, PreflightResponse } from "../../types";
import { duration as formatDuration } from "../../utils/format";

/** One labelled value on the review screen, as a headline metric or a summary row. */
export interface LabelledValue {
  label: string;
  value: string;
}

/** Headline numbers, shown for whichever of them preflight was able to estimate. */
export function reviewMetrics(
  request: MeasurementRequest | undefined,
  preflight: PreflightResponse | undefined,
  definition: MeasureDefinition | undefined,
): LabelledValue[] {
  if (!request || !preflight) return [];
  const { estimated_variations: variations, estimated_duration_seconds: seconds } = preflight;
  const metrics: LabelledValue[] =
    variations === undefined && seconds === undefined
      ? []
      : [
          { label: "Variations", value: String(variations ?? "—") },
          { label: "Estimated time", value: seconds === undefined ? "—" : formatDuration(seconds) },
        ];
  for (const [field, values] of multiSelections(request, definition)) {
    metrics.push({ label: field.label, value: String(values.length) });
  }
  const probe = preflight.light_load_probe;
  if (probe?.points.length) {
    metrics.push(
      { label: "Low-load checks", value: String(probe.checked_variations) },
      { label: "Lowest aggregate load", value: `${probe.minimum_aggregate_power_w.toFixed(3)} W` },
    );
  }
  return metrics;
}

/** Everything the review screen restates about the pending measurement, in the order it reads. */
export function reviewSummary(
  request: MeasurementRequest | undefined,
  preflight: PreflightResponse | undefined,
  definition: MeasureDefinition | undefined,
): LabelledValue[] {
  if (!request) return [];
  const battery = batterySource(request, preflight);
  return [
    { label: "Type", value: definition?.label ?? request.measure_type },
    ...profileRows(request),
    ...controllerRows(request, definition),
    ...reviewFieldRows(request, definition),
    { label: "Power", value: summarize(request.power_meter) },
    ...multiSelectionRows(request, definition),
    ...(battery ? [{ label: "Battery", value: battery }] : []),
    ...(request.dummy_load ? [{ label: "Dummy load", value: dummyLoadSummary(request.dummy_load) }] : []),
  ];
}

function profileRows(request: MeasurementRequest): LabelledValue[] {
  const rows: LabelledValue[] = [];
  if (request.session_name) rows.push({ label: "Session", value: request.session_name });
  if (request.measure_device) rows.push({ label: "Device", value: request.measure_device });
  return rows;
}

/** Name the controller with the label the server gave its field — "Light", "Media player", … */
function controllerRows(request: MeasurementRequest, definition?: MeasureDefinition): LabelledValue[] {
  const controller = definition?.fields.find((field) => field.role === "controller");
  if (!controller) return [];
  const entity = requestFieldValue(request, controller);
  const value = Array.isArray(entity) ? entity.join(", ") : entity;
  return [{ label: controller.label, value: typeof value === "string" && value ? value : "Virtual device" }];
}

function reviewFieldRows(request: MeasurementRequest, definition?: MeasureDefinition): LabelledValue[] {
  return (definition?.fields.filter((field) => field.review) ?? []).flatMap((field) => {
    const value = requestFieldValue(request, field);
    if (value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) return [];
    const values = Array.isArray(value) ? value : [String(value)];
    const formatted = values.map((item) => field.options.find((option) => option.value === item)?.label ?? item);
    const label = field.plural_label && formatted.length > 1 ? field.plural_label : field.label;
    return [{ label, value: formatted.join(", ") }];
  });
}

function multiSelectionRows(request: MeasurementRequest, definition?: MeasureDefinition): LabelledValue[] {
  return multiSelections(request, definition).map(([field, values]) => ({ label: field.label, value: values.join(", ") }));
}

/**
 * Multi-select fields of the pending request, paired with what it selected. Controller
 * fields (a multi-light `light_entity_id`) and `review` fields are left out: both are
 * already restated by `controllerRows` and `reviewFieldRows`, under their own label.
 */
function multiSelections(request: MeasurementRequest, definition?: MeasureDefinition): [FormField, string[]][] {
  return (definition?.fields ?? [])
    .filter((field) => field.control === "multi_select" || (field.control === "entity" && field.multiple))
    .filter((field) => field.role !== "controller" && !field.review)
    .flatMap((field) => {
      const values = requestFieldValue(request, field);
      return Array.isArray(values) ? [[field, values] as [FormField, string[]]] : [];
    });
}

/** Where the battery level is read from, when preflight found one. */
function batterySource(request: MeasurementRequest, preflight?: PreflightResponse): string | undefined {
  if (!preflight) return undefined;
  if (preflight.battery_level_entity_id) return preflight.battery_level_entity_id;
  const { controller } = request as { controller?: { type: string; entity_id?: string } };
  if (!preflight.battery_level_attribute || controller?.type !== "hass") return undefined;
  return `${controller.entity_id} · ${preflight.battery_level_attribute} attribute`;
}

function dummyLoadSummary(dummyLoad: NonNullable<MeasurementRequest["dummy_load"]>): string {
  return dummyLoad.mode === "reuse"
    ? `${dummyLoad.description} (${dummyLoad.resistance} Ω, saved calibration)`
    : `${dummyLoad.description} (calibrate before measurement)`;
}
