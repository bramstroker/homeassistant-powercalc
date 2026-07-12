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

export interface EntityDescriptor {
  entity_id: string;
  name: string;
  state?: string;
  unit?: string;
  supported_modes?: LutMode[];
  effect_list?: string[];
}

export interface MeasureDefaults {
  sleep_time: number;
  sample_count: number;
  brightness_step: number;
  hue_step: number;
  saturation_step: number;
  color_temp_step: number;
}

export interface Capabilities {
  modes: LutMode[];
  defaults: MeasureDefaults;
  limits?: Record<string, { min: number; max: number }>;
}

export type MeasureType = "Light bulb(s)" | "Smart speaker" | "Recorder" | "Average" | "Charging device" | "Fan";

export interface FormField {
  name: string;
  label: string;
  control: "entity" | "number" | "text" | "boolean" | "select";
  required: boolean;
  entity_domain?: string | null;
  options: { value: string; label: string }[];
  default?: string | number | boolean | null;
}

export interface MeasureDefinition {
  measure_type: MeasureType;
  label: string;
  description: string;
  fields: FormField[];
  supports_profile: boolean;
  supports_resume: boolean;
}

export interface MeasurementRunRequest {
  measure_type: MeasureType;
  model_id: string;
  product_name: string;
  measure_device: string;
  answers: Record<string, string | number | boolean>;
  generate_model: boolean;
  sleep_time: number;
  sample_count: number;
  resume_policy: "new";
}

export interface MeasurementRequest {
  model_id: string;
  product_name: string;
  measure_device: string;
  light_entity_id: string;
  power_entity_id: string;
  voltage_entity_id: string | null;
  modes: LutMode[];
  generate_model: boolean;
  gzip: boolean;
  multiple_light_count: number;
  sleep_time: number;
  sample_count: number;
  brightness_step: number;
  hue_step: number;
  saturation_step: number;
  color_temp_step: number;
  resume_policy: "new" | "resume" | "overwrite";
}

export interface PreflightResponse {
  valid: boolean;
  warnings: string[];
  estimated_variations?: number;
  estimated_duration_seconds?: number;
  supported_modes?: LutMode[];
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
  mode?: string | null;
  progress?: SessionProgress;
  warnings?: string[];
  error?: { code?: string; message: string } | string | null;
  request?: MeasurementRequest;
}

export interface SessionFile {
  name: string;
  size: number;
  media_type: string;
}

export interface SessionEvent {
  type: "progress" | "state" | "warning" | "log" | "checkpoint" | "heartbeat" | "sample";
  snapshot?: SessionSnapshot;
  message?: string;
  progress?: SessionProgress;
  phase?: string;
  mode?: string;
  power?: number;
}

export interface AppSettings {
  default_power_entity_id: string | null;
  default_measure_device: string | null;
  power_meter: "hass" | "shelly" | "dummy" | null;
  shelly_ip: string | null;
}

export interface PowerMeterTestResult {
  success: boolean;
  power?: number | null;
  message?: string | null;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  field: string | null;
}
