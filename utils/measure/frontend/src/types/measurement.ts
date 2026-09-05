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
  device_id?: string | null;
  integration?: string | null;
  manufacturer?: string | null;
  model_id?: string | null;
  product_name?: string | null;
  state?: string;
  unit?: string | null;
  attribute_names?: string[];
  supported_modes?: LutMode[] | null;
  effect_list?: string[] | null;
  min_mired?: number | null;
  max_mired?: number | null;
  related_voltage_entity_id?: string | null;
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

export interface ManufacturerCatalog {
  manufacturers: string[];
}

export interface DeviceSpecificationField {
  name: string;
  label: string;
  description: string;
  value_type: "string" | "number" | "integer" | "boolean";
  collection: "scalar" | "array" | "scalar_or_array";
  options: string[];
}

export interface DeviceSpecificationCatalog {
  device_types: Record<string, DeviceSpecificationField[]>;
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
  session_name?: string;
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
  gzip?: boolean;
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
  export_filename?: string;
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
