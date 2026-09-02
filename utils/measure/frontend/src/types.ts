export type SettingsSection = "power_meter" | "measure_tuning" | "github";

export type SessionState =
  | "idle"
  | "validating"
  | "ready"
  | "awaiting_confirmation"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed"
  | "resumable";

export type LutMode = "brightness" | "color_temp" | "hs" | "effect";
export type DeviceClass = "power" | "voltage" | "battery";
export type ChargingDeviceType = "vacuum_robot" | "lawn_mower_robot";
export type ResumePolicy = "new" | "resume";
/** Derived from the spec union so a new meter variant automatically widens it. */
export type PowerMeterType = PowerMeterSpec["type"];

export type OperatingPoint =
  | { type: "light"; on: boolean; brightness?: number; color_temp_mired?: number; hue?: number; saturation?: number; effect?: string }
  | { type: "speaker"; volume: number; muted: boolean }
  | { type: "fan"; percentage: number; on: boolean }
  | { type: "charging"; battery_level: number; charging: boolean };

export interface EntityDescriptor {
  entity_id: string;
  name: string;
  domain?: string;
  device_class?: DeviceClass | null;
  device_id?: string;
  model_id?: string;
  state?: string;
  unit?: string;
  supported_modes?: LutMode[];
  effect_list?: string[];
  related_voltage_entity_id?: string;
  member_entity_ids?: string[];
}

export interface EntityCatalog {
  lights: EntityDescriptor[];
  powers: EntityDescriptor[];
  voltages: EntityDescriptor[];
}

export interface MeasureDeviceCatalog {
  devices: string[];
}

export interface MeasurementParameters {
  sleep_time: number;
  sample_count: number;
  sleep_time_sample: number;
  max_retries: number;
  max_nudges: number;
  bri_bri_steps: number;
  ct_bri_steps: number;
  ct_mired_steps: number;
  hs_bri_steps: number;
  hs_hue_steps: number;
  hs_sat_steps: number;
  min_brightness: number;
  sleep_initial: number;
  sleep_standby: number;
  effect_bri_steps: number;
  measure_time_effect: number;
  measure_time_effect_min: number;
}

/** Name of a tuning parameter, so a lookup keyed by one cannot name a parameter that does not exist. */
export type MeasureParameterName = keyof MeasurementParameters;

export interface Capabilities {
  runtime_version: string;
  defaults: MeasurementParameters;
  limits?: Partial<Record<MeasureParameterName, { min: number; max: number }>>;
  developer_mode?: boolean;
  fast_test_mode?: boolean;
}

export type MeasureType = "light" | "speaker" | "recorder" | "average" | "charging" | "fan";

/** A plain value as it travels between the app and the API: form field values, device info, metadata. */
export type PrimitiveValue = string | number | boolean | null;

/** Where a submitted field value lands in the measurement request. Mirrors `FieldRole` server-side. */
export type FieldRole = "attribute" | "controller" | "power_meter";

export interface FormFieldOption {
  value: string;
  label: string;
  entity_domain?: string | null;
  /** Measurement parameters that only apply while this option is selected. */
  enables?: string[];
  description?: string;
  guidance?: string[];
}

export interface FormField {
  name: string;
  label: string;
  control: "entity" | "number" | "text" | "boolean" | "select" | "multi_select";
  role: FieldRole;
  /** Controller field whose selected entity limits this field's options to what it supports. */
  narrowed_by?: string | null;
  required: boolean;
  entity_domains?: string[];
  options: FormFieldOption[];
  default?: PrimitiveValue;
  minimum?: number | null;
  maximum?: number | null;
  /** Whether several entities can be selected for this field at once. */
  multiple?: boolean;
  /** Label to use while several entities are selected. */
  plural_label?: string;
  /** Entity field whose number of selected entities this count follows by default. */
  derived_from?: string | null;
  hint?: string;
  visible_when?: Record<string, string[]>;
  all_entities?: boolean;
  entity_device_classes?: DeviceClass[];
  related_to?: string | null;
  same_device_only?: boolean;
  review?: boolean;
}

/** A tuning parameter as one measure type presents it. Bounds come from `Capabilities.limits`. */
export interface MeasureParameter {
  name: MeasureParameterName;
  label: string;
  hint?: string;
  step?: string;
  /** Heading this parameter is grouped under, repeated on each member of the group. */
  group?: string;
  /** Only applies while the named parameter is greater than one. */
  requires_multiple?: MeasureParameterName | null;
}

export interface MeasureDefinition {
  measure_type: MeasureType;
  label: string;
  description: string;
  icon: string;
  fields: FormField[];
  parameters: MeasureParameter[];
  supports_profile: boolean;
  supports_resume: boolean;
  confirmation_action?: string | null;
  confirmation_is_warning?: boolean;
  /** Placeholders shown in the profile fields, to steer the naming this type expects. */
  model_id_example: string;
  product_name_example: string;
}

export interface BaseMeasurementRequest {
  model_id: string;
  product_name: string;
  measure_device: string;
  generate_model: boolean;
  parameters: MeasurementParameters;
  resume_policy: ResumePolicy;
  power_meter: PowerMeterSpec;
  dummy_load?: DummyLoadSpec | null;
}

export type DummyLoadSpec =
  | { mode: "calibrate"; description: string }
  | { mode: "reuse"; description: string; resistance: number };

export interface DummyLoadCalibration {
  description: string;
  resistance: number;
  calibrated_at: string;
  power_meter_fingerprint?: string;
}

/** The subset of tuning parameters the app keeps as reusable defaults across sessions. */
export type AppMeasurementDefaults = Pick<
  MeasurementParameters,
  "sleep_time" | "sample_count" | "sleep_time_sample" | "max_retries" | "max_nudges"
>;

export type PowerMeterSpec =
  | { type: "dummy" }
  | { type: "hass"; entity_id: string; voltage_entity_id?: string | null; call_update_entity?: boolean }
  | { type: "shelly"; device_ip: string; username?: string; timeout?: number }
  | { type: "kasa"; device_ip: string };

export type LightControllerSpec =
  | { type: "dummy" }
  | { type: "hass"; entity_id: string; transition_time?: number }
  | { type: "hass_multi"; entity_ids: string[]; transition_time?: number }
  | { type: "hue"; bridge_ip: string; light: string };

export type MediaControllerSpec = { type: "dummy" } | { type: "hass"; entity_id: string };
export type ChargingControllerSpec = { type: "dummy" } | { type: "hass"; entity_id: string };
export type FanControllerSpec = { type: "dummy" } | { type: "hass"; entity_id: string };

export interface LightMeasurementRequest extends BaseMeasurementRequest {
  measure_type: "light";
  controller: LightControllerSpec;
  modes: LutMode[];
  gzip: boolean;
  multiple_light_count: number;
}

export interface AverageMeasurementRequest extends BaseMeasurementRequest { measure_type: "average"; controller?: null; duration: number; }
export interface RecorderMeasurementRequest extends BaseMeasurementRequest {
  measure_type: "recorder";
  controller?: null;
  recorder_purpose: "playbook" | "complex_profile";
  profile_recipe?: "generic" | "vacuum_robot" | null;
  tracked_entity_ids?: string[];
  vacuum_entity_id?: string | null;
  battery_entity_id?: string | null;
  additional_entity_ids?: string[];
}
export interface SpeakerMeasurementRequest extends BaseMeasurementRequest { measure_type: "speaker"; controller: MediaControllerSpec; disable_streaming: boolean; }
export interface ChargingMeasurementRequest extends BaseMeasurementRequest { measure_type: "charging"; controller: ChargingControllerSpec; charging_device_type: ChargingDeviceType; }
export interface FanMeasurementRequest extends BaseMeasurementRequest { measure_type: "fan"; controller: FanControllerSpec; }

export type MeasurementRequest =
  | LightMeasurementRequest
  | AverageMeasurementRequest
  | RecorderMeasurementRequest
  | SpeakerMeasurementRequest
  | ChargingMeasurementRequest
  | FanMeasurementRequest;

export interface PreflightResponse {
  valid: boolean;
  warnings: string[];
  estimated_variations?: number;
  estimated_duration_seconds?: number;
  supported_modes?: LutMode[];
  power_meter_diagnostic?: PowerMeterDiagnostic | null;
  battery_level_entity_id?: string | null;
  battery_level_attribute?: string | null;
  light_load_probe?: {
    checked_variations: number;
    minimum_aggregate_power_w: number;
    points: {
      label: string;
      mode: LutMode;
      power_w: number;
    }[];
  } | null;
}

export interface SessionProgress {
  completed: number;
  total: number;
  skipped?: number;
  percent?: number;
  estimated_remaining_seconds?: number | null;
}

export interface SessionSnapshot {
  session_id?: string;
  state: SessionState;
  created_at?: string;
  updated_at?: string;
  phase?: string;
  confirmation_message?: string | null;
  confirmation_action?: string | null;
  mode?: string | null;
  progress?: SessionProgress;
  warnings?: string[];
  error?: { code?: string; message: string } | string | null;
  summary?: Record<string, string> | null;
  request?: MeasurementRequest;
  operating_point?: OperatingPoint | null;
  calibration_sample?: {
    power: number;
    resistance: number;
    voltage: number;
  } | null;
  entity_states?: Record<string, string>;
}

export interface SessionSummary {
  session_id: string;
  state: SessionState;
  created_at: string;
  updated_at: string;
  measure_type: MeasureType;
  model_id: string;
  product_name: string;
  measure_device: string;
  completed: number;
  total: number;
  percent: number;
  can_resume: boolean;
  file_count: number;
  size: number;
  active: boolean;
}

export interface SessionFile {
  name: string;
  size: number;
  media_type: string;
}

export interface PlotPoint {
  x: number;
  y: number;
  color: string | null;
}

export interface PlotSeries {
  label: string | null;
  color: string | null;
  points: PlotPoint[];
}

export interface PlotSpec {
  id: string;
  title: string;
  kind: "scatter" | "line";
  x_label: string;
  y_label: string;
  source: string;
  series: PlotSeries[];
}

export interface PlotCollection {
  partial: boolean;
  plots: PlotSpec[];
  warnings: string[];
}

/** A collection with nothing plotted yet, used as the initial and the reset value. */
export function emptyPlots(warnings: string[] = []): PlotCollection {
  return { partial: false, plots: [], warnings };
}

/**
 * Payload of a regular session event. Progress, phase and state all reach the app through the
 * snapshot that rides along with the event, so only live/log fields are read from the payload.
 */
export interface SessionEventData {
  message?: string;
  power?: number;
  resistance?: number;
  voltage?: number;
  states?: Record<string, string>;
}

/** Event types the stream subscribes to. The server sends each one as its own SSE event name. */
export const REGULAR_SESSION_EVENT_TYPES = [
  "phase",
  "progress",
  "state",
  "warning",
  "log",
  "checkpoint",
  "heartbeat",
  "sample",
  "calibration_sample",
  "entity_states",
] as const;

export const SESSION_EVENT_TYPES = [...REGULAR_SESSION_EVENT_TYPES, "operating_point"] as const;

interface RegularSessionEvent {
  sequence: number;
  type: (typeof REGULAR_SESSION_EVENT_TYPES)[number];
  data: SessionEventData;
  snapshot?: SessionSnapshot;
}

interface OperatingPointSessionEvent {
  sequence: number;
  type: "operating_point";
  data: OperatingPoint;
  snapshot?: SessionSnapshot;
}

export type SessionEvent = RegularSessionEvent | OperatingPointSessionEvent;

export interface AppSettings {
  default_power_entity_id: string | null;
  default_measure_device: string | null;
  power_meter: PowerMeterType | null;
  shelly_ip: string | null;
  shelly_username?: string;
  shelly_password_configured?: boolean;
  kasa_ip: string | null;
  fast_test_mode: boolean;
  measurement_defaults: AppMeasurementDefaults;
}

export interface AppSettingsUpdate extends AppSettings {
  shelly_password?: string | null;
  clear_shelly_password?: boolean;
}

export interface ContributionIdentity {
  login: string;
}

export interface ContributionAuthState {
  connected: boolean;
  device_flow_available?: boolean;
  identity?: ContributionIdentity | null;
  method?: "device" | "token" | null;
  scopes?: string[];
  permissions_verified?: boolean;
}

export interface ContributionDeviceFlow {
  flow_id: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete?: string | null;
  expires_in: number;
  interval: number;
}

export interface ContributionAuthDeviceStatus {
  status: "pending" | "slow_down" | "authorized" | "expired" | "denied";
  auth?: ContributionAuthState | null;
  message?: string | null;
  retry_after?: number | null;
}

export interface ContributionTokenRequest {
  token: string;
}

export interface ContributionDraftFile {
  path: string;
  content?: string | null;
  rendered_json?: unknown;
}

export interface ContributionDraft {
  eligible: boolean;
  reason?: string | null;
  repository: string;
  fork_repository?: string | null;
  base_branch: string;
  base_sha?: string | null;
  manufacturer_name: string;
  manufacturer_directory: string;
  manufacturer_library_url?: string | null;
  model_id: string;
  product_name: string;
  contributor: string;
  device_info: Record<string, PrimitiveValue>;
  home_assistant: Record<string, PrimitiveValue>;
  notes: string;
  files: ContributionDraftFile[];
  model_json?: unknown;
  commit_message: string;
  pr_title: string;
  pr_body: string;
  branch_name: string;
  job_id?: string | null;
}

export interface ContributionPreviewRequest {
  manufacturer_name: string;
  manufacturer_directory: string;
  model_id: string;
  product_name: string;
  contributor: string;
  notes: string;
}

export interface ContributionPreview extends ContributionDraft {
  warnings: string[];
}

export interface ContributionSubmitRequest extends ContributionPreviewRequest {
  confirmed: true;
}

export interface ContributionResult {
  status: "success" | "failed" | "pending";
  message?: string | null;
  repository?: string | null;
  branch_name?: string | null;
  pull_request_url?: string | null;
}

export type ContributionState = "idle" | "preview_ready" | "submitting" | "submitted" | "failed";

export interface ContributionStatus {
  state: ContributionState;
  session_id?: string | null;
  preview?: ContributionPreview | null;
  submission_url?: string | null;
  message?: string | null;
  error?: string | null;
  updated_at?: string | null;
}

export interface ShellyDiscoveryDevice {
  id: string;
  name: string;
  model: string | null;
  generation: number | null;
  ip_address: string;
  supported: boolean;
  reason: string | null;
  auth_required: boolean;
}

export interface ShellyDiscoveryResponse {
  devices: ShellyDiscoveryDevice[];
  available: boolean;
  message: string | null;
}

export type DiagnosticStatus = "good" | "warning" | "poor" | "unsupported";
export type PrecisionStatus = "good" | "poor" | "unsupported";

export interface PowerMeterDiagnostic {
  success: boolean;
  power?: number | null;
  supports_voltage?: boolean | null;
  status: DiagnosticStatus;
  precision_decimals?: number | null;
  max_report_interval_seconds?: number | null;
  reports_observed: number;
  duration_seconds: number;
  precision_status: PrecisionStatus;
  update_interval_status: DiagnosticStatus;
  messages: string[];
  message?: string | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  field: string | null;
  help_url?: string | null;
  help_label?: string | null;
}

export interface ErrorHelp {
  url: string;
  label: string;
}
