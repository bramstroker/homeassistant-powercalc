import { duration as formatDuration } from "./format";
import { requestFieldValue } from "./measure-definition";
import { summarize } from "./power-meter";
import type { FormField, MeasureDefinition, MeasurementRequest, PreflightResponse } from "./types";

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
  const rows: LabelledValue[] = [{ label: "Type", value: definition?.label ?? request.measure_type }];
  if (definition?.supports_profile) rows.push({ label: "Model", value: `${request.product_name} (${request.model_id})` });
  if (request.measure_device) rows.push({ label: "Device", value: request.measure_device });

  // Name the controller with the label the server gave its field — "Light", "Media player", …
  const controller = definition?.fields.find((field) => field.role === "controller");
  if (controller) {
    const entity = requestFieldValue(request, controller);
    const value = Array.isArray(entity) ? entity.join(", ") : entity;
    rows.push({ label: controller.label, value: typeof value === "string" && value ? value : "Virtual device" });
  }

  for (const field of definition?.fields.filter((candidate) => candidate.review) ?? []) {
    const value = requestFieldValue(request, field);
    if (value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) continue;
    const values = Array.isArray(value) ? value : [String(value)];
    const formatted = values.map((item) => field.options.find((option) => option.value === item)?.label ?? item);
    rows.push({ label: field.plural_label && formatted.length > 1 ? field.plural_label : field.label, value: formatted.join(", ") });
  }

  rows.push({ label: "Power", value: summarize(request.power_meter) });
  for (const [field, values] of multiSelections(request, definition).filter(([field]) => !field.review)) {
    rows.push({ label: field.label, value: values.join(", ") });
  }
  const battery = batterySource(request, preflight);
  if (battery) rows.push({ label: "Battery", value: battery });
  if (request.dummy_load) rows.push({ label: "Dummy load", value: dummyLoadSummary(request.dummy_load) });
  return rows;
}

/** Multi-select fields of the pending request, paired with what it selected. */
function multiSelections(request: MeasurementRequest, definition?: MeasureDefinition): [FormField, string[]][] {
  return (definition?.fields ?? [])
    .filter((field) => field.control === "multi_select" || (field.control === "entity" && field.multiple))
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
