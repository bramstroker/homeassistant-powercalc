import type {
  ApiErrorBody,
  AppSettings,
  Capabilities,
  ContributionAuthDeviceStatus,
  ContributionAuthState,
  ContributionDeviceFlow,
  ContributionPreview,
  ContributionResult,
  ContributionStatus,
  DeviceSpecificationCatalog,
  DummyLoadCalibration,
  DummyLoadSpec,
  EntityCatalog,
  EntityDescriptor,
  ManufacturerCatalog,
  MeasureDefinition,
  MeasureDeviceCatalog,
  MeasurementRequest,
  OperatingPoint,
  PlotCollection,
  PowerMeterDiagnostic,
  PowerMeterSpec,
  PreflightResponse,
  SessionEvent,
  SessionFile,
  SessionSnapshot,
  SessionSummary,
  ShellyDiscoveryResponse,
} from "./types";

export type Decoder<T> = (value: unknown) => T;
type Guard<T> = (value: unknown) => value is T;
type Shape = Record<string, Guard<unknown>>;
type ShapeValue<S extends Shape> = { [K in keyof S]: S[K] extends Guard<infer T> ? T : never };

const isUnknown: Guard<unknown> = (_value): _value is unknown => true;
const isBoolean: Guard<boolean> = (value): value is boolean => typeof value === "boolean";
const isString: Guard<string> = (value): value is string => typeof value === "string";
const isNumber: Guard<number> = (value): value is number => typeof value === "number" && Number.isFinite(value);
const isInteger: Guard<number> = (value): value is number => isNumber(value) && Number.isInteger(value);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function objectOf<S extends Shape>(shape: S): Guard<ShapeValue<S>> {
  return (value): value is ShapeValue<S> => {
    if (!isRecord(value)) return false;
    for (const key in shape) {
      const guard = shape[key];
      if (!guard || !guard(value[key])) return false;
    }
    return true;
  };
}

function arrayOf<T>(guard: Guard<T>): Guard<T[]> {
  return (value): value is T[] => Array.isArray(value) && value.every(guard);
}

function recordOf<T>(guard: Guard<T>): Guard<Record<string, T>> {
  return (value): value is Record<string, T> => isRecord(value) && Object.values(value).every(guard);
}

function optional<T>(guard: Guard<T>): Guard<T | undefined> {
  return (value): value is T | undefined => value === undefined || guard(value);
}

function nullable<T>(guard: Guard<T>): Guard<T | null> {
  return (value): value is T | null => value === null || guard(value);
}

function optionalNullable<T>(guard: Guard<T>): Guard<T | null | undefined> {
  return optional(nullable(guard));
}

function oneOf<const T extends readonly (string | number | boolean)[]>(...values: T): Guard<T[number]> {
  return (value): value is T[number] => values.some((candidate) => candidate === value);
}

function decoder<T>(description: string, guard: Guard<T>): Decoder<T> {
  return (value: unknown): T => {
    if (!guard(value)) throw new Error(`Invalid ${description} response from the measure app.`);
    return value;
  };
}

const isStringArray = arrayOf(isString);
const isStringRecord = recordOf(isString);
const isPrimitive = (value: unknown): value is string | number | boolean | null =>
  value === null || isString(value) || isNumber(value) || isBoolean(value);

const isPowerMeterSpec: Guard<PowerMeterSpec> = (value): value is PowerMeterSpec => {
  if (!isRecord(value) || !isString(value.type)) return false;
  switch (value.type) {
    case "dummy": return true;
    case "hass":
      return isString(value.entity_id) && optionalNullable(isString)(value.voltage_entity_id)
        && optional(isBoolean)(value.call_update_entity);
    case "shelly":
      return isString(value.device_ip) && optional(isString)(value.username) && optional(isNumber)(value.timeout);
    case "kasa": return isString(value.device_ip);
    default: return false;
  }
};

const isLightController = (value: unknown): boolean => {
  if (!isRecord(value) || !isString(value.type)) return false;
  if (value.type === "dummy") return true;
  if (value.type === "hass") return isString(value.entity_id) && optional(isNumber)(value.transition_time);
  if (value.type === "hass_multi") return isStringArray(value.entity_ids) && optional(isNumber)(value.transition_time);
  return value.type === "hue" && isString(value.bridge_ip) && isString(value.light);
};

const isHassOrDummyController = (value: unknown): boolean =>
  isRecord(value)
  && (value.type === "dummy" || (value.type === "hass" && isString(value.entity_id)));

const isDummyLoadSpec: Guard<DummyLoadSpec> = (value): value is DummyLoadSpec => {
  if (!isRecord(value) || !isString(value.description) || value.description.trim() === "") return false;
  if (value.mode === "calibrate") return true;
  return value.mode === "reuse" && isNumber(value.resistance) && value.resistance > 0;
};

const parameterNames = [
  "sleep_time", "sample_count", "sleep_time_sample", "max_retries", "max_nudges", "bri_bri_steps",
  "ct_bri_steps", "ct_mired_steps", "hs_bri_steps", "hs_hue_steps", "hs_sat_steps", "min_brightness",
  "sleep_initial", "sleep_standby", "effect_bri_steps", "measure_time_effect", "measure_time_effect_min",
] as const;

const isMeasurementParameters: Guard<Capabilities["defaults"]> = (value): value is Capabilities["defaults"] => {
  if (!recordOf((entry): entry is number | boolean => isNumber(entry) || isBoolean(entry))(value)) return false;
  return parameterNames.every((name) => isNumber(value[name]));
};

export const isMeasurementRequest: Guard<MeasurementRequest> = (value): value is MeasurementRequest => {
  if (!isRecord(value)
    || !oneOf("light", "speaker", "recorder", "average", "charging", "fan")(value.measure_type)
    || !isString(value.model_id)
    || !isString(value.product_name)
    || !isString(value.measure_device)
    || !isBoolean(value.generate_model)
    || !isMeasurementParameters(value.parameters)
    || !oneOf("new", "resume")(value.resume_policy)
    || !isPowerMeterSpec(value.power_meter)
    || !optional(isString)(value.session_name)
    || !optionalNullable(isDummyLoadSpec)(value.dummy_load)) {
    return false;
  }
  switch (value.measure_type) {
    case "light":
      return isLightController(value.controller) && isStringArray(value.modes)
        && value.modes.every(oneOf("brightness", "color_temp", "hs", "effect"))
        && optional(isBoolean)(value.gzip) && isInteger(value.multiple_light_count);
    case "speaker": return isHassOrDummyController(value.controller) && isBoolean(value.disable_streaming);
    case "charging": return isHassOrDummyController(value.controller) && oneOf("vacuum_robot", "lawn_mower_robot")(value.charging_device_type);
    case "fan": return isHassOrDummyController(value.controller);
    case "average": return (value.controller === null || value.controller === undefined) && isInteger(value.duration);
    case "recorder":
      return (value.controller === null || value.controller === undefined)
        && oneOf("playbook", "complex_profile")(value.recorder_purpose)
        && optionalNullable(oneOf("generic", "vacuum_robot"))(value.profile_recipe)
        && optional(isStringArray)(value.tracked_entity_ids)
        && optionalNullable(isString)(value.vacuum_entity_id)
        && optionalNullable(isString)(value.battery_entity_id)
        && optional(isStringArray)(value.additional_entity_ids)
        && isString(value.export_filename);
  }
};

const isEntityDescriptor: Guard<EntityDescriptor> = objectOf({
  entity_id: isString,
  name: isString,
  domain: optional(isString),
  device_class: optionalNullable(oneOf("power", "voltage", "battery")),
  device_id: optionalNullable(isString),
  integration: optionalNullable(isString),
  manufacturer: optionalNullable(isString),
  model_id: optionalNullable(isString),
  product_name: optionalNullable(isString),
  state: optional(isString),
  unit: optionalNullable(isString),
  attribute_names: optional(isStringArray),
  supported_modes: optionalNullable(arrayOf(oneOf("brightness", "color_temp", "hs", "effect"))),
  effect_list: optionalNullable(isStringArray),
  min_mired: optionalNullable(isInteger),
  max_mired: optionalNullable(isInteger),
  related_voltage_entity_id: optionalNullable(isString),
  member_entity_ids: optional(isStringArray),
});

const isFormFieldOption = objectOf({
  value: isString, label: isString, entity_domain: optionalNullable(isString), enables: optional(isStringArray),
  description: optional(isString), guidance: optional(isStringArray),
});
const isFormField = objectOf({
  name: isString,
  label: isString,
  control: oneOf("entity", "number", "text", "boolean", "select", "multi_select"),
  role: oneOf("attribute", "controller", "power_meter"),
  narrowed_by: optionalNullable(isString),
  required: isBoolean,
  entity_domains: optional(isStringArray),
  options: arrayOf(isFormFieldOption),
  default: optional(isPrimitive),
  minimum: optionalNullable(isNumber),
  maximum: optionalNullable(isNumber),
  multiple: optional(isBoolean),
  plural_label: optional(isString),
  derived_from: optionalNullable(isString),
  hint: optional(isString),
  visible_when: optional(recordOf(isStringArray)),
  all_entities: optional(isBoolean),
  entity_device_classes: optional(arrayOf(oneOf("power", "voltage", "battery"))),
  related_to: optionalNullable(isString),
  same_device_only: optional(isBoolean),
  review: optional(isBoolean),
});
const isMeasureParameter = objectOf({
  name: oneOf(...parameterNames), label: isString, hint: optional(isString), step: optional(isString),
  group: optional(isString), requires_multiple: optionalNullable(oneOf(...parameterNames)),
});
const isMeasureDefinition: Guard<MeasureDefinition> = objectOf({
  measure_type: oneOf("light", "speaker", "recorder", "average", "charging", "fan"),
  label: isString,
  description: isString,
  icon: isString,
  fields: arrayOf(isFormField),
  parameters: arrayOf(isMeasureParameter),
  supports_profile: isBoolean,
  supports_resume: isBoolean,
  confirmation_action: optionalNullable(isString),
  confirmation_is_warning: optional(isBoolean),
  model_id_example: isString,
  product_name_example: isString,
});

const isAppMeasurementDefaults = objectOf({
  sleep_time: isNumber, sample_count: isNumber, sleep_time_sample: isNumber, max_retries: isNumber, max_nudges: isNumber,
});
const isAppSettings: Guard<AppSettings> = objectOf({
  default_power_entity_id: nullable(isString),
  default_measure_device: nullable(isString),
  default_measure_device_firmware: optionalNullable(isString),
  default_contributor_name: optionalNullable(isString),
  default_contributor_github: optionalNullable(isString),
  default_contributor_email: optionalNullable(isString),
  power_meter: nullable(oneOf("hass", "shelly", "kasa", "dummy")),
  shelly_ip: nullable(isString),
  shelly_username: optional(isString),
  shelly_password_configured: optional(isBoolean),
  kasa_ip: nullable(isString),
  fast_test_mode: isBoolean,
  measurement_defaults: isAppMeasurementDefaults,
});

const isContributionAuth: Guard<ContributionAuthState> = objectOf({
  connected: isBoolean,
  device_flow_available: optional(isBoolean),
  identity: optionalNullable(objectOf({ login: isString })),
  method: optionalNullable(oneOf("device", "token", "none")),
  scopes: optional(isStringArray),
  permissions_verified: optional(isBoolean),
});
const isContributionDeviceFlow: Guard<ContributionDeviceFlow> = objectOf({
  flow_id: isString, user_code: isString, verification_uri: isString,
  verification_uri_complete: optionalNullable(isString), expires_in: isNumber, interval: isNumber,
});
const isContributionAuthDeviceStatus: Guard<ContributionAuthDeviceStatus> = objectOf({
  status: oneOf("pending", "slow_down", "authorized", "expired", "denied"),
  auth: optionalNullable(isContributionAuth), message: optionalNullable(isString), retry_after: optionalNullable(isNumber),
});

const isContributionFile = objectOf({
  path: isString, size: optional(isNumber), content: optionalNullable(isString), rendered_json: optional(isUnknown),
});
const isPrimitiveRecord = recordOf(isPrimitive);
const isContributionPreview: Guard<ContributionPreview> = objectOf({
  eligible: isBoolean,
  reason: optionalNullable(isString),
  repository: isString,
  fork_repository: optionalNullable(isString),
  base_branch: isString,
  base_sha: optionalNullable(isString),
  manufacturer_name: isString,
  manufacturer_directory: isString,
  manufacturer_library_url: optionalNullable(isString),
  model_id: isString,
  product_name: isString,
  contributor: isString,
  contributor_github: optional(isString),
  contributor_email: optional(isString),
  aliases: optional(isStringArray),
  gtins: optional(isStringArray),
  product_url: optional(isString),
  mains_voltage: optionalNullable(isNumber),
  voltage_range: optionalNullable(objectOf({ min: isNumber, max: isNumber })),
  device_specs: optionalNullable(recordOf(isUnknown)),
  device_type: optional(isString),
  measure_device: optional(isString),
  measure_device_firmware: optional(isString),
  measure_description: optional(isString),
  device_info: isPrimitiveRecord,
  home_assistant: isPrimitiveRecord,
  notes: isString,
  files: arrayOf(isContributionFile),
  model_json: optional(isUnknown),
  commit_message: isString,
  pr_title: isString,
  pr_body: isString,
  branch_name: isString,
  job_id: optionalNullable(isString),
  warnings: isStringArray,
});
const isContributionResult: Guard<ContributionResult> = objectOf({
  status: oneOf("success", "failed", "pending"), message: optionalNullable(isString),
  repository: optionalNullable(isString), branch_name: optionalNullable(isString), pull_request_url: optionalNullable(isString),
});
const isContributionStatus: Guard<ContributionStatus> = objectOf({
  state: oneOf("idle", "preview_ready", "submitting", "submitted", "failed"),
  session_id: optionalNullable(isString), preview: optionalNullable(isContributionPreview),
  submission_url: optionalNullable(isString), message: optionalNullable(isString), error: optionalNullable(isString),
  updated_at: optionalNullable(isString),
});

const isDiagnostic: Guard<PowerMeterDiagnostic> = objectOf({
  success: isBoolean, power: optionalNullable(isNumber), supports_voltage: optionalNullable(isBoolean),
  status: oneOf("good", "warning", "poor", "unsupported"), precision_decimals: optionalNullable(isNumber),
  max_report_interval_seconds: optionalNullable(isNumber), reports_observed: isNumber, duration_seconds: isNumber,
  precision_status: oneOf("good", "poor", "unsupported"),
  update_interval_status: oneOf("good", "warning", "poor", "unsupported"), messages: isStringArray,
  message: optionalNullable(isString),
});
const isPreflight: Guard<PreflightResponse> = objectOf({
  valid: isBoolean, warnings: isStringArray, estimated_variations: optionalNullable(isNumber),
  estimated_duration_seconds: optionalNullable(isNumber), supported_modes: optionalNullable(arrayOf(oneOf("brightness", "color_temp", "hs", "effect"))),
  power_meter_diagnostic: optionalNullable(isDiagnostic), battery_level_entity_id: optionalNullable(isString),
  battery_level_attribute: optionalNullable(isString),
  light_load_probe: optionalNullable(objectOf({
    checked_variations: isNumber, minimum_aggregate_power_w: isNumber,
    points: arrayOf(objectOf({ label: isString, mode: oneOf("brightness", "color_temp", "hs", "effect"), power_w: isNumber })),
  })),
});

const isOperatingPoint: Guard<OperatingPoint> = (value): value is OperatingPoint => {
  if (!isRecord(value) || !isString(value.type)) return false;
  switch (value.type) {
    case "light": return isBoolean(value.on) && optional(isNumber)(value.brightness)
      && optional(isNumber)(value.color_temp_mired) && optional(isNumber)(value.hue)
      && optional(isNumber)(value.saturation) && optional(isString)(value.effect);
    case "speaker": return isNumber(value.volume) && isBoolean(value.muted);
    case "fan": return isNumber(value.percentage) && isBoolean(value.on);
    case "charging": return isNumber(value.battery_level) && isBoolean(value.charging);
    default: return false;
  }
};
const isSessionState = oneOf(
  "idle", "validating", "ready", "awaiting_confirmation", "running", "cancelling",
  "cancelled", "completed", "failed", "resumable",
);
const isSessionProgress = objectOf({
  completed: isInteger, total: isInteger, skipped: isInteger, percent: isNumber,
  estimated_remaining_seconds: nullable(isInteger),
});
const isSessionSnapshot: Guard<SessionSnapshot> = objectOf({
  session_id: isString,
  state: isSessionState,
  created_at: isString, updated_at: isString, phase: nullable(isString),
  confirmation_message: nullable(isString), confirmation_action: nullable(isString), mode: nullable(isString),
  progress: isSessionProgress, warnings: isStringArray, error: nullable(isString),
  summary: nullable(isStringRecord), request: isMeasurementRequest, operating_point: nullable(isOperatingPoint),
  calibration_sample: nullable(objectOf({ power: isNumber, resistance: isNumber, voltage: isNumber })),
  entity_states: isStringRecord,
});
const isSessionSummary: Guard<SessionSummary> = objectOf({
  session_id: isString,
  state: isSessionState,
  created_at: isString, updated_at: isString,
  measure_type: oneOf("light", "speaker", "recorder", "average", "charging", "fan"),
  model_id: isString, product_name: isString, measure_device: isString, completed: isNumber, total: isNumber,
  percent: isNumber, can_resume: isBoolean, file_count: isNumber, size: isNumber, active: isBoolean,
});

const isPlotCollection: Guard<PlotCollection> = objectOf({
  partial: isBoolean,
  plots: arrayOf(objectOf({
    id: isString, title: isString, kind: oneOf("scatter", "line"), x_label: isString, y_label: isString,
    source: isString, series: arrayOf(objectOf({
      label: nullable(isString), color: nullable(isString),
      points: arrayOf(objectOf({ x: isNumber, y: isNumber, color: nullable(isString) })),
    })),
  })),
  warnings: isStringArray,
});

export const decodeCapabilities: Decoder<Capabilities> = decoder("capabilities", (value): value is Capabilities =>
  objectOf({ runtime_version: isString, defaults: isMeasurementParameters, limits: optional(recordOf(objectOf({ min: isNumber, max: isNumber }))),
    developer_mode: optional(isBoolean), fast_test_mode: optional(isBoolean) })(value));
export const decodeMeasureDefinitions = decoder("measurement definitions", arrayOf(isMeasureDefinition));
export const decodeMeasureDevices: Decoder<MeasureDeviceCatalog> = decoder("measure-device catalog", objectOf({ devices: isStringArray }));
export const decodeManufacturers: Decoder<ManufacturerCatalog> = decoder("manufacturer catalog", objectOf({ manufacturers: isStringArray }));
export const decodeDeviceSpecifications: Decoder<DeviceSpecificationCatalog> = decoder("device-specification catalog", objectOf({ device_types: recordOf(arrayOf(objectOf({
  name: isString, label: isString, description: isString, value_type: oneOf("string", "number", "integer", "boolean"),
  collection: oneOf("scalar", "array", "scalar_or_array"), options: isStringArray,
}))) }));
export const decodeSettings = decoder("settings", isAppSettings);
export const decodeContributionAuth = decoder("contribution authentication", isContributionAuth);
export const decodeContributionDeviceFlow = decoder("contribution device flow", isContributionDeviceFlow);
export const decodeContributionAuthDeviceStatus = decoder("contribution device status", isContributionAuthDeviceStatus);
export const decodeContributionStatus = decoder("contribution status", isContributionStatus);
export const decodePowerMeterDiagnostic = decoder("power-meter diagnostic", isDiagnostic);
export const decodeShellyDiscovery: Decoder<ShellyDiscoveryResponse> = decoder("Shelly discovery", objectOf({
  devices: arrayOf(objectOf({ id: isString, name: isString, model: nullable(isString), generation: nullable(isNumber),
    ip_address: isString, supported: isBoolean, reason: nullable(isString), auth_required: isBoolean })),
  available: isBoolean, message: nullable(isString),
}));
export const decodeEntityCatalog: Decoder<EntityCatalog> = decoder("entity catalog", objectOf({
  lights: arrayOf(isEntityDescriptor), powers: arrayOf(isEntityDescriptor), voltages: arrayOf(isEntityDescriptor),
}));
export const decodeEntities = decoder("entity list", arrayOf(isEntityDescriptor));
export const decodeDummyLoadCalibration: Decoder<DummyLoadCalibration | null> = decoder("dummy-load calibration", nullable(objectOf({
  description: isString, resistance: isNumber, calibrated_at: isString, power_meter_fingerprint: optional(isString),
})));
export const decodePreflight = decoder("preflight", isPreflight);
export const decodeSessionSnapshot = decoder("session snapshot", isSessionSnapshot);
export const decodeSessionSummaries = decoder("session list", arrayOf(isSessionSummary));
export const decodeSessionFiles: Decoder<SessionFile[]> = decoder("session files", arrayOf(objectOf({ name: isString, size: isNumber, media_type: isString })));
export const decodePlots = decoder("plots", isPlotCollection);
export const decodeContributionPreview = decoder("contribution preview", isContributionPreview);
export const decodeContributionResult = decoder("contribution result", isContributionResult);

export function decodeApiError(value: unknown): Partial<ApiErrorBody> & { detail?: unknown } {
  if (!isRecord(value)) return {};
  return {
    code: isString(value.code) ? value.code : undefined,
    message: isString(value.message) ? value.message : undefined,
    field: value.field === null || isString(value.field) ? value.field : undefined,
    help_url: value.help_url === null || isString(value.help_url) ? value.help_url : undefined,
    help_label: value.help_label === null || isString(value.help_label) ? value.help_label : undefined,
    detail: value.detail,
  };
}

interface DecodedSessionEnvelope {
  event?: SessionEvent;
  snapshot?: SessionSnapshot;
}

export function decodeSessionEnvelope(value: unknown): DecodedSessionEnvelope {
  if (!isRecord(value) || !isInteger(value.sequence) || !isString(value.type) || !isRecord(value.data)) {
    throw new Error("Invalid event envelope");
  }
  const snapshot = value.snapshot === undefined ? undefined : decodeSessionSnapshot(value.snapshot);
  if (value.type === "operating_point") {
    if (!isOperatingPoint(value.data)) throw new Error("Invalid operating-point event");
    return { event: { sequence: value.sequence, type: value.type, data: value.data, snapshot }, snapshot };
  }
  if (!isRegularEventType(value.type)) {
    return {
      event: snapshot
        ? { sequence: value.sequence, type: "heartbeat", data: {}, snapshot }
        : undefined,
      snapshot,
    };
  }
  switch (value.type) {
    case "phase":
    case "warning":
    case "log":
      if (!isString(value.data.message)) throw new Error("Invalid message event");
      break;
    case "checkpoint":
      if (!isString(value.data.message) || !optionalNullable(isString)(value.data.action)) {
        throw new Error("Invalid checkpoint event");
      }
      break;
    case "progress":
      if (!(isInteger(value.data.completed) && isInteger(value.data.total) && isInteger(value.data.skipped)
        && isString(value.data.mode) && isString(value.data.estimated_remaining))) {
        throw new Error("Invalid progress event");
      }
      break;
    case "state":
      if (!isSessionState(value.data.state) || !optionalNullable(isString)(value.data.error)) {
        throw new Error("Invalid state event");
      }
      break;
    case "sample":
      if (!isNumber(value.data.power)) throw new Error("Invalid sample event");
      break;
    case "calibration_sample":
      if (!(isNumber(value.data.power) && isNumber(value.data.resistance) && isNumber(value.data.voltage))) {
        throw new Error("Invalid calibration event");
      }
      break;
    case "entity_states":
      if (!isStringRecord(value.data.states)) throw new Error("Invalid entity-state event");
      break;
    case "heartbeat":
      break;
  }
  return { event: { sequence: value.sequence, type: value.type, data: value.data, snapshot }, snapshot };
}

function isRegularEventType(value: string): value is Exclude<SessionEvent["type"], "operating_point"> {
  return ["phase", "progress", "state", "warning", "log", "checkpoint", "heartbeat", "sample", "calibration_sample", "entity_states"].includes(value);
}
