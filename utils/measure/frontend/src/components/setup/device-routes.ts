import type { MeasureDefinition, MeasureType, MeasurementRequest } from "../../types";

export const FREE_MEASUREMENT = "free_measurement";

export interface DeviceChoice {
  id: string;
  label: string;
  experimental?: boolean;
}

export interface MeasurementRoute {
  id: string;
  measureType: MeasureType;
  label: string;
  description: string;
  preset: Record<string, string>;
  recommended?: boolean;
  experimental?: boolean;
}

export interface RouteSelection {
  deviceId: string;
  routeId: string;
}

const SPECIALIZED_DEVICES: Partial<Record<MeasureType, DeviceChoice>> = {
  light: { id: "light", label: "Light" },
  speaker: { id: "smart_speaker", label: "Smart speaker" },
  fan: { id: "fan", label: "Fan" },
};

function fieldOptions(definition: MeasureDefinition | undefined, name: string) {
  return definition?.fields.find((field) => field.name === name)?.options ?? [];
}

/** Use the server's supported profile types as the device catalog. */
export function deviceChoices(definitions: MeasureDefinition[]): DeviceChoice[] {
  const choices = new Map<string, DeviceChoice>();
  for (const option of fieldOptions(definitions.find((item) => item.measure_type === "recorder"), "profile_device_type")) {
    choices.set(option.value, { id: option.value, label: option.label });
  }
  for (const definition of definitions) {
    const device = SPECIALIZED_DEVICES[definition.measure_type];
    if (device && !choices.has(device.id)) choices.set(device.id, device);
  }
  const charging = definitions.find((item) => item.measure_type === "charging");
  for (const option of fieldOptions(charging, "charging_device_type")) {
    if (!choices.has(option.value)) choices.set(option.value, { id: option.value, label: option.label });
  }
  const recorder = definitions.find((item) => item.measure_type === "recorder");
  if (fieldOptions(recorder, "profile_recipe").some((option) => option.value === "vacuum_robot")) {
    choices.set("vacuum_robot", { id: "vacuum_robot", label: "Robot vacuum" });
  }
  return [...choices.values()]
    .map((choice) => {
      const routes = routesForDevice(choice.id, definitions);
      return { ...choice, experimental: routes.some((route) => route.experimental) };
    })
    .sort((left, right) => left.label.localeCompare(right.label));
}

/** A route is offered only when its measurement definition is available. */
export function routesForDevice(deviceId: string, definitions: MeasureDefinition[]): MeasurementRoute[] {
  const available = new Set(definitions.map((definition) => definition.measure_type));
  const routes: MeasurementRoute[] = [];
  if (deviceId === FREE_MEASUREMENT) {
    if (available.has("average")) routes.push({
      id: "average", measureType: "average", label: "Measure average power",
      description: "Get one average reading for a device state.", preset: {},
    });
    if (available.has("recorder")) routes.push({
      id: "playbook", measureType: "recorder", label: "Record a Playbook cycle",
      description: "Save power over time as a Playbook CSV.", preset: { recorder_purpose: "playbook" },
    });
    return routes;
  }
  if (deviceId === "light") {
    return available.has("light") ? [{
      id: "light", measureType: "light", label: "Automated light measurement",
      description: "Measure brightness, color and effects for a light profile.", preset: {},
    }] : [];
  }
  if (deviceId === "smart_speaker") {
    return available.has("speaker") ? [{
      id: "speaker", measureType: "speaker", label: "Measure volume levels",
      description: "Automatically calibrate playback power across volume levels.", preset: {},
    }] : [];
  }
  if (deviceId === "fan" && available.has("fan")) routes.push({
    id: "fan", measureType: "fan", label: "Measure fan speeds",
    description: "Automatically calibrate power across percentage levels.", preset: {},
  });
  if (deviceId === "vacuum_robot" && available.has("recorder")) {
    routes.push({
      id: "vacuum_profile", measureType: "recorder", label: "Record vacuum and dock activity",
      description: "Capture activity states and charging for a complex profile.",
      preset: { recorder_purpose: "complex_profile", profile_recipe: "vacuum_robot" },
      recommended: true,
      experimental: true,
    });
  }
  if (["vacuum_robot", "lawn_mower_robot"].includes(deviceId) && available.has("charging")) routes.push({
    id: "charging", measureType: "charging", label: "Measure charging power",
    description: "Calibrate power against battery level while charging.", preset: { charging_device_type: deviceId },
    experimental: deviceId === "lawn_mower_robot",
  });
  if (deviceId === "lawn_mower_robot" || !available.has("recorder")) return routes;
  if (deviceId !== "vacuum_robot" && fieldOptions(definitions.find((item) => item.measure_type === "recorder"), "profile_device_type")
    .some((option) => option.value === deviceId)) {
    routes.push({
      id: "complex_profile", measureType: "recorder", label: "Record device states",
      description: "Record power and Home Assistant states for a complex profile.",
      preset: { recorder_purpose: "complex_profile", profile_recipe: "generic", profile_device_type: deviceId },
      experimental: true,
    });
  }
  return routes;
}

/** Map old saved requests to the new entry flow without changing their schema. */
export function selectionFromRequest(request: MeasurementRequest): RouteSelection {
  switch (request.measure_type) {
    case "light": return { deviceId: "light", routeId: "light" };
    case "speaker": return { deviceId: "smart_speaker", routeId: "speaker" };
    case "fan": return { deviceId: "fan", routeId: "fan" };
    case "charging": return { deviceId: request.charging_device_type, routeId: "charging" };
    case "average": return { deviceId: FREE_MEASUREMENT, routeId: "average" };
    case "recorder":
      if (request.recorder_purpose === "playbook") return { deviceId: FREE_MEASUREMENT, routeId: "playbook" };
      if (request.profile_recipe === "vacuum_robot") return { deviceId: "vacuum_robot", routeId: "vacuum_profile" };
      return { deviceId: request.profile_device_type ?? "generic_iot", routeId: "complex_profile" };
  }
}
