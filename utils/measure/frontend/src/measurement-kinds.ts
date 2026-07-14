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
}

export const MEASUREMENT_KINDS: Record<MeasureType, MeasurementKindMetadata> = {
  light: { icon: "💡" },
  speaker: { icon: "🔊" },
  recorder: { icon: "⏺" },
  average: { icon: "📊" },
  charging: { icon: "🔋" },
  fan: { icon: "🌀" },
};

export function measurementIcon(type: MeasureType): string {
  return MEASUREMENT_KINDS[type].icon;
}

export function deviceFields(definition: MeasureDefinition): FormField[] {
  return definition.fields.filter((field) => field.name !== "power_entity_id");
}

export function requestFieldValue(request: NonLightMeasurementRequest, name: string): string | number | boolean | undefined {
  switch (request.measure_type) {
    case "average": return name === "duration" ? request.duration : undefined;
    case "recorder": return name === "export_filename" ? request.export_filename : undefined;
    case "speaker": return speakerFieldValue(request, name);
    case "charging": return chargingFieldValue(request, name);
    case "fan": return name === "fan_entity_id" ? hassEntityId(request.controller) : undefined;
  }
}

function speakerFieldValue(request: Extract<NonLightMeasurementRequest, { measure_type: "speaker" }>, name: string): string | boolean | undefined {
  if (name === "media_player_entity_id") return hassEntityId(request.controller);
  return name === "disable_streaming" ? request.disable_streaming : undefined;
}

function chargingFieldValue(request: Extract<NonLightMeasurementRequest, { measure_type: "charging" }>, name: string): string | undefined {
  if (name === "charging_entity_id") return hassEntityId(request.controller);
  return name === "charging_device_type" ? request.charging_device_type : undefined;
}

function hassEntityId(controller: { type: string; entity_id?: string }): string | undefined {
  return controller.type === "hass" ? controller.entity_id : undefined;
}

export function entityDomain(definition: MeasureDefinition, field: FormField, selectedOption?: string): string | undefined {
  if (field.name === "charging_entity_id") {
    const options = definition.fields.find((candidate) => candidate.name === "charging_device_type")?.options ?? [];
    return options.find((option) => option.value === selectedOption)?.entity_domain ?? undefined;
  }
  return field.entity_domains?.[0];
}

export function entityDomains(definition: MeasureDefinition, values?: FormData): string[] {
  return definition.fields
    .filter((field) => field.control === "entity" && field.name !== "power_entity_id" && field.name !== "light_entity_id")
    .flatMap((field) => {
      if (field.name !== "charging_entity_id") return field.entity_domains ?? [];
      const options = definition.fields.find((candidate) => candidate.name === "charging_device_type")?.options ?? [];
      if (values) return [entityDomain(definition, field, text(values, "charging_device_type"))];
      return options.map((option) => option.entity_domain);
    })
    .filter((domain): domain is string => Boolean(domain));
}

export function buildNonLightRequest(
  definition: MeasureDefinition,
  form: FormData,
  capabilities: Capabilities,
  powerMeter: PowerMeterSpec,
): NonLightMeasurementRequest {
  if (definition.measure_type === LIGHT_TYPE) throw new Error("Light requests use the specialized form");

  const parameter = (name: keyof Capabilities["defaults"]): number => {
    const value = form.get(name);
    return typeof value === "string" && value !== "" ? Number(value) : capabilities.defaults[name];
  };

  const base: BaseMeasurementRequest = {
    model_id: text(form, "model_id") || "measurement",
    product_name: text(form, "product_name") || definition.label,
    measure_device: text(form, "measure_device"),
    power_meter: powerMeter,
    generate_model: definition.supports_profile,
    parameters: {
      ...capabilities.defaults,
      sleep_time: parameter("sleep_time"),
      sample_count: parameter("sample_count"),
      sleep_time_sample: parameter("sleep_time_sample"),
      sleep_standby: parameter("sleep_standby"),
    },
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
