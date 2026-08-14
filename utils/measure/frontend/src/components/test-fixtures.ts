import type {
  AppSettings,
  Capabilities,
  DummyLoadCalibration,
  EntityDescriptor,
  ErrorHelp,
  MeasureDefinition,
  MeasureParameter,
  MeasureParameterName,
  MeasurementRequest,
  PowerMeterDiagnostic,
  PowerMeterSpec,
} from "../types";
import type { MeasureAppController } from "../app-controller";
import type { AppShell } from "./app-shell";

/** Fixtures and element shapes shared by the view tests. */

export const measurementDefaults = { sleep_time: 1, sample_count: 5, sleep_time_sample: 1, max_retries: 5, max_nudges: 0 };
export const defaultSettings: AppSettings = {
  default_power_entity_id: null, default_measure_device: null, power_meter: "hass", shelly_ip: null, kasa_ip: null,
  fast_test_mode: false,
  measurement_defaults: measurementDefaults,
};
export const capabilities: Capabilities = {
  runtime_version: "v0.2.1:app",
  defaults: {
    ...measurementDefaults,
    bri_bri_steps: 1, ct_bri_steps: 5, ct_mired_steps: 10,
    hs_bri_steps: 32, hs_hue_steps: 2731, hs_sat_steps: 32,
    min_brightness: 1, sleep_initial: 10, sleep_standby: 20,
    effect_bri_steps: 40, measure_time_effect: 180, measure_time_effect_min: 20,
  },
};

export const goodPowerMeterDiagnostic: PowerMeterDiagnostic = {
  success: true,
  power: 12.3,
  status: "good",
  precision_decimals: 2,
  max_report_interval_seconds: 1.8,
  reports_observed: 7,
  duration_seconds: 12,
  precision_status: "good",
  update_interval_status: "good",
  messages: ["The sensor meets the recommended update frequency."],
};

/** The setup view under test, with the reactive properties these tests drive. */
export type SetupViewElement = HTMLElement & {
  capabilities: Capabilities;
  definitions: MeasureDefinition[];
  initialRequest?: MeasurementRequest;
  lights: EntityDescriptor[];
  powers: EntityDescriptor[];
  voltages: EntityDescriptor[];
  deviceEntities: Record<string, EntityDescriptor[]>;
  deviceEntityErrors: Record<string, string>;
  dummyLoadCalibration: DummyLoadCalibration | null;
  selectedType: string;
  selectedEntities: Record<string, string[]>;
  multipleLights: boolean;
  meter: PowerMeterSpec;
  powerMeterConfigured: boolean;
  defaultMeasureDevice: string;
  errorMessage: string;
  errorHelp?: ErrorHelp;
  busy: boolean;
  updateComplete: Promise<boolean>;
  shadowRoot: ShadowRoot;
};

/** The shell wires its views straight to the controller, so a test drives the controller itself. */
export const controllerOf = (element: AppShell): MeasureAppController =>
  (element as unknown as { controller: MeasureAppController }).controller;

export const modeParameter = (name: MeasureParameterName, label: string) => ({ name, label, group: "Profile resolution" });

export const lightDefinition: MeasureDefinition = {
  measure_type: "light",
  label: "Light bulb(s)",
  description: "Build a lookup-table power profile for a light.",
  icon: "💡",
  model_id_example: "LWA017",
  product_name_example: "Philips Hue White Ambiance A60 E27",
  parameters: [
    { name: "sleep_time", label: "Settle time (seconds)", hint: "Wait after changing the light before reading power.", step: "0.1", group: "Sampling" },
    { name: "sample_count", label: "Samples per point", hint: "More samples reduce noise but increase measurement time.", group: "Sampling" },
    { name: "sleep_time_sample", label: "Time between samples (seconds)", hint: "Only used when taking more than one sample.", group: "Sampling", requires_multiple: "sample_count" },
    { name: "min_brightness", label: "Minimum brightness", group: "Sampling" },
    { name: "sleep_initial", label: "Initial stabilization (seconds)", group: "Sampling" },
    { name: "sleep_standby", label: "Standby stabilization (seconds)", group: "Sampling" },
    modeParameter("bri_bri_steps", "Brightness mode step"),
    modeParameter("ct_bri_steps", "Color temperature brightness step"),
    modeParameter("ct_mired_steps", "Color temperature mired step"),
    modeParameter("hs_bri_steps", "HS brightness step"),
    modeParameter("hs_hue_steps", "HS hue step"),
    modeParameter("hs_sat_steps", "HS saturation step"),
    modeParameter("effect_bri_steps", "Effect brightness step"),
    modeParameter("measure_time_effect_min", "Minimum time per effect (seconds)"),
    modeParameter("measure_time_effect", "Maximum time per effect (seconds)"),
  ],
  fields: [
    { name: "power_entity_id", role: "power_meter", label: "Power sensor", control: "entity", required: true, entity_domains: ["sensor"], options: [] },
    { name: "light_entity_id", role: "controller", label: "Light", plural_label: "Lights", control: "entity", required: true, multiple: true, entity_domains: ["light"], options: [] },
    {
      name: "modes",
      role: "attribute",
      label: "Lookup-table modes",
      control: "multi_select",
      narrowed_by: "light_entity_id",
      required: true,
      options: [
        { value: "brightness", label: "Brightness", enables: ["bri_bri_steps"] },
        { value: "color_temp", label: "Color temperature", enables: ["ct_bri_steps", "ct_mired_steps"] },
        { value: "hs", label: "Hue & saturation", enables: ["hs_bri_steps", "hs_hue_steps", "hs_sat_steps"] },
        { value: "effect", label: "Effect", enables: ["effect_bri_steps", "measure_time_effect_min", "measure_time_effect"] },
      ],
    },
    { name: "multiple_light_count", role: "attribute", label: "Number of lights", control: "number", required: true, options: [], default: 1, minimum: 1, maximum: 100, derived_from: "light_entity_id" },
  ],
  supports_profile: true,
  supports_resume: true,
};

export const lights: EntityDescriptor[] = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"] }];

export const definitions: MeasureDefinition[] = [
  lightDefinition,
  {
    measure_type: "average",
        icon: "📊",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }] satisfies MeasureParameter[],
    label: "Average",
    description: "Measure average power for a fixed duration.",
    fields: [
      { name: "power_entity_id", role: "power_meter", label: "Power sensor", control: "entity", required: true, options: [] },
      { name: "duration", role: "attribute", label: "Duration (seconds)", control: "number", required: true, options: [], default: 60 },
    ],
    supports_profile: false,
    supports_resume: false,
  },
];
