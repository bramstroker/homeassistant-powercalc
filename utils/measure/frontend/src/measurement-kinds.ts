import type {
  BaseMeasurementRequest,
  Capabilities,
  FormField,
  MeasureDefinition,
  MeasureType,
  NonLightMeasurementRequest,
  PowerMeterSpec,
} from "./types";

export const LIGHT_TYPE = "light" as const;

interface MeasurementKindMetadata {
  icon: string;
  entityField?: "media_player_entity_id" | "charging_entity_id" | "fan_entity_id";
}

export const MEASUREMENT_KINDS: Record<MeasureType, MeasurementKindMetadata> = {
  light: { icon: "💡" },
  speaker: { icon: "🔊", entityField: "media_player_entity_id" },
  recorder: { icon: "⏺" },
  average: { icon: "📊" },
  charging: { icon: "🔋", entityField: "charging_entity_id" },
  fan: { icon: "🌀", entityField: "fan_entity_id" },
};

export function measurementIcon(type: MeasureType): string {
  return MEASUREMENT_KINDS[type].icon;
}

/** Normalize pre-refactor field names while persisted clients and servers are upgraded. */
export function canonicalFieldName(type: MeasureType, name: string): string {
  if (name === "powermeter_entity_id") return "power_entity_id";
  if (name === "entity_id") return MEASUREMENT_KINDS[type].entityField ?? name;
  return name;
}

export function canonicalFields(definition: MeasureDefinition): FormField[] {
  return definition.fields.map((field) => ({ ...field, name: canonicalFieldName(definition.measure_type, field.name) }));
}

export function deviceFields(definition: MeasureDefinition): FormField[] {
  return canonicalFields(definition).filter((field) => field.name !== "power_entity_id");
}

export function requestFieldValue(request: NonLightMeasurementRequest, name: string): string | number | boolean | undefined {
  const field = canonicalFieldName(request.measure_type, name);
  switch (request.measure_type) {
    case "average": return field === "duration" ? request.duration : undefined;
    case "recorder": return field === "export_filename" ? request.export_filename : undefined;
    case "speaker":
      if (field === "media_player_entity_id") return request.controller.type === "hass" ? request.controller.entity_id : undefined;
      return field === "disable_streaming" ? request.disable_streaming : undefined;
    case "charging":
      if (field === "charging_entity_id") return request.controller.type === "hass" ? request.controller.entity_id : undefined;
      return field === "charging_device_type" ? request.charging_device_type : undefined;
    case "fan": return field === "fan_entity_id" && request.controller.type === "hass" ? request.controller.entity_id : undefined;
  }
}

export function entityDomain(type: MeasureType, field: FormField, values?: FormData): string | undefined {
  if (type === "charging" && canonicalFieldName(type, field.name) === "charging_entity_id") {
    return values?.get("charging_device_type") === "lawn_mower_robot" ? "lawn_mower" : "vacuum";
  }
  return field.entity_domain ?? undefined;
}

export function entityDomains(definition: MeasureDefinition, values?: FormData): string[] {
  return canonicalFields(definition)
    .filter((field) => field.control === "entity" && field.name !== "power_entity_id" && field.name !== "light_entity_id")
    .flatMap((field) => field.entity_domains?.length ? field.entity_domains : [entityDomain(definition.measure_type, field, values)])
    .filter((domain): domain is string => Boolean(domain));
}

export function buildNonLightRequest(
  definition: MeasureDefinition,
  form: FormData,
  capabilities: Capabilities,
  powerMeter: PowerMeterSpec,
): NonLightMeasurementRequest {
  if (definition.measure_type === LIGHT_TYPE) throw new Error("Light requests use the specialized form");

  const base: BaseMeasurementRequest = {
    model_id: text(form, "model_id") || "measurement",
    product_name: text(form, "product_name") || definition.label,
    measure_device: text(form, "measure_device"),
    power_meter: powerMeter,
    generate_model: definition.supports_profile,
    parameters: { ...capabilities.defaults },
    resume_policy: "new",
  };

  switch (definition.measure_type) {
    case "average": return { ...base, measure_type: "average", duration: number(form, "duration") };
    case "recorder": return { ...base, measure_type: "recorder", export_filename: text(form, "export_filename") };
    case "speaker": return {
      ...base,
      measure_type: "speaker",
      controller: { type: "hass", entity_id: text(form, "media_player_entity_id") },
      disable_streaming: form.has("disable_streaming"),
    };
    case "charging": return {
      ...base,
      measure_type: "charging",
      controller: { type: "hass", entity_id: text(form, "charging_entity_id") },
      charging_device_type: text(form, "charging_device_type") as "vacuum_robot" | "lawn_mower_robot",
    };
    case "fan": return {
      ...base,
      measure_type: "fan",
      controller: { type: "hass", entity_id: text(form, "fan_entity_id") },
    };
  }
}

function text(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function number(form: FormData, name: string): number {
  return Number(text(form, name));
}
