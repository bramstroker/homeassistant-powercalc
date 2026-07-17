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
export type DeviceClass = "power" | "voltage";

export type OperatingPoint =
  | { type: "light"; on: boolean; brightness?: number; color_temp_mired?: number; hue?: number; saturation?: number; effect?: string }
  | { type: "speaker"; volume: number; muted: boolean }
  | { type: "fan"; percentage: number; on: boolean }
  | { type: "charging"; battery_level: number; charging: boolean };

export interface EntityDescriptor {
  entity_id: string;
  name: string;
  device_id?: string;
  model_id?: string;
  state?: string;
  unit?: string;
  supported_modes?: LutMode[];
  effect_list?: string[];
  related_voltage_entity_id?: string;
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

export type MeasureDefaults = MeasurementParameters;

export interface Capabilities {
  modes: LutMode[];
  defaults: MeasureDefaults;
  limits?: Record<string, { min: number; max: number }>;
}

export type MeasureType = "light" | "speaker" | "recorder" | "average" | "charging" | "fan";

export interface FormField {
  name: string;
  label: string;
  control: "entity" | "number" | "text" | "boolean" | "select";
  required: boolean;
  entity_domains?: string[];
  options: { value: string; label: string; entity_domain?: string | null }[];
  default?: string | number | boolean | null;
  minimum?: number | null;
  maximum?: number | null;
}

export interface MeasureDefinition {
  measure_type: MeasureType;
  label: string;
  description: string;
  fields: FormField[];
  supports_profile: boolean;
  supports_resume: boolean;
  confirmation_action?: string | null;
}

export interface BaseMeasurementRequest {
  model_id: string;
  product_name: string;
  measure_device: string;
  generate_model: boolean;
  parameters: MeasurementParameters;
  resume_policy: "new" | "resume" | "overwrite";
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

export interface AppMeasurementDefaults {
  sleep_time: number;
  sample_count: number;
  sleep_time_sample: number;
  max_retries: number;
  max_nudges: number;
}

export type PowerMeterSpec =
  | { type: "dummy" }
  | { type: "hass"; entity_id: string; voltage_entity_id?: string | null; call_update_entity?: boolean }
  | { type: "shelly"; device_ip: string; timeout?: number };

export type LightControllerSpec =
  | { type: "dummy" }
  | { type: "hass"; entity_id: string; transition_time?: number }
  | { type: "hue"; bridge_ip: string; light: string };

export type MediaControllerSpec = { type: "dummy" } | { type: "hass"; entity_id: string };
export type ChargingControllerSpec = { type: "dummy" } | { type: "hass"; entity_id: string };
export type FanControllerSpec = { type: "dummy" } | { type: "hass"; entity_id: string };

export interface LightMeasurementRequest extends BaseMeasurementRequest {
  measure_type: "light";
  controller: LightControllerSpec;
  modes: LutMode[];
  generate_model: boolean;
  gzip: boolean;
  multiple_light_count: number;
}

export interface AverageMeasurementRequest extends BaseMeasurementRequest { measure_type: "average"; duration: number; }
export interface RecorderMeasurementRequest extends BaseMeasurementRequest { measure_type: "recorder"; export_filename: string; }
export interface SpeakerMeasurementRequest extends BaseMeasurementRequest { measure_type: "speaker"; controller: MediaControllerSpec; disable_streaming: boolean; }
export interface ChargingMeasurementRequest extends BaseMeasurementRequest { measure_type: "charging"; controller: ChargingControllerSpec; charging_device_type: "vacuum_robot" | "lawn_mower_robot"; }
export interface FanMeasurementRequest extends BaseMeasurementRequest { measure_type: "fan"; controller: FanControllerSpec; }

export type NonLightMeasurementRequest =
  | AverageMeasurementRequest
  | RecorderMeasurementRequest
  | SpeakerMeasurementRequest
  | ChargingMeasurementRequest
  | FanMeasurementRequest;

export type MeasurementRequest = LightMeasurementRequest | NonLightMeasurementRequest;

export interface PreflightResponse {
  valid: boolean;
  warnings: string[];
  estimated_variations?: number;
  estimated_duration_seconds?: number;
  supported_modes?: LutMode[];
  power_meter_diagnostic?: PowerMeterDiagnostic | null;
}

export interface SessionProgress {
  completed: number;
  total: number;
  percent?: number;
  estimated_remaining_seconds?: number | null;
}

export interface SessionSnapshot {
  session_id?: string;
  state: SessionState;
  phase?: string;
  confirmation_message?: string | null;
  mode?: string | null;
  progress?: SessionProgress;
  warnings?: string[];
  error?: { code?: string; message: string } | string | null;
  summary?: Record<string, string> | null;
  request?: MeasurementRequest;
  operating_point?: OperatingPoint | null;
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

export interface SessionEventData {
  message?: string;
  power?: number;
  completed?: number;
  total?: number;
  mode?: string;
  estimated_remaining?: string;
  state?: SessionState;
  error?: string | null;
}

interface RegularSessionEvent {
  sequence: number;
  type: "phase" | "progress" | "state" | "warning" | "log" | "checkpoint" | "heartbeat" | "sample";
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
  power_meter: "hass" | "shelly" | "dummy" | null;
  shelly_ip: string | null;
  measurement_defaults: AppMeasurementDefaults;
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

export interface PowerMeterDiagnostic {
  success: boolean;
  power?: number | null;
  status: DiagnosticStatus;
  precision_decimals?: number | null;
  max_report_interval_seconds?: number | null;
  reports_observed: number;
  duration_seconds: number;
  precision_status: "good" | "poor" | "unsupported";
  update_interval_status: DiagnosticStatus;
  messages: string[];
  message?: string | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  field: string | null;
}
