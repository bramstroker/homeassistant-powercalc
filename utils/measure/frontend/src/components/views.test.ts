import type { AppSettings, AppSettingsUpdate, Capabilities, DummyLoadCalibration, EntityDescriptor, ErrorHelp, MeasureDefinition, MeasurementRequest, OperatingPoint, PowerMeterDiagnostic, PreflightResponse, SessionSnapshot, SettingsSection } from "../types";
import { sharedStyles } from "../styles";
import { AppShell } from "./app-shell";
import "./result-view";
import "./running-view";
import "./settings-view";
import "./setup-view";

const measurementDefaults = { sleep_time: 1, sample_count: 5, sleep_time_sample: 1, max_retries: 5, max_nudges: 0 };
const defaultSettings: AppSettings = {
  default_power_entity_id: null, default_measure_device: null, power_meter: "hass", shelly_ip: null, kasa_ip: null,
  fast_test_mode: false,
  measurement_defaults: measurementDefaults,
};
const capabilities: Capabilities = {
  runtime_version: "v0.2.1:app",
  defaults: {
    ...measurementDefaults,
    bri_bri_steps: 1, ct_bri_steps: 5, ct_mired_steps: 10,
    hs_bri_steps: 32, hs_hue_steps: 2731, hs_sat_steps: 32,
    min_brightness: 1, sleep_initial: 10, sleep_standby: 20,
    effect_bri_steps: 40, measure_time_effect: 180, measure_time_effect_min: 20,
  },
};

const goodPowerMeterDiagnostic: PowerMeterDiagnostic = {
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
type SetupViewElement = HTMLElement & {
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
  powerMeter: string;
  powerMeterConfigured: boolean;
  shellyIp: string;
  kasaIp: string;
  defaultPowerEntityId: string;
  defaultMeasureDevice: string;
  errorMessage: string;
  errorHelp?: ErrorHelp;
  busy: boolean;
  updateComplete: Promise<boolean>;
  shadowRoot: ShadowRoot;
};

const modeParameter = (name: string, label: string) => ({ name, label, group: "Profile resolution" });

const lightDefinition: MeasureDefinition = {
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

const lights: EntityDescriptor[] = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"] }];

it("uses dark native form controls so iOS select indicators remain visible", () => {
  expect(sharedStyles.cssText).toContain("color-scheme: dark");
});

describe("setup view", () => {
  it("renders dynamic entities, mode choices, and collapsed advanced settings", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.selectedEntities = { light_entity_id: ["light.desk"] };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Desk lamp · light.desk");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.querySelector("details")?.open).toBe(false);
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
    expect((element.shadowRoot.querySelector('input[name="sleep_time"]') as HTMLInputElement).value).toBe("1");
    expect((element.shadowRoot.querySelector('input[name="sleep_time_sample"]') as HTMLInputElement).disabled).toBe(false);
    expect((element.shadowRoot.querySelector('input[name="bri_bri_steps"]') as HTMLInputElement).value).toBe("1");
    // The desk lamp supports brightness only, so no other mode's parameters are offered at all.
    const unsupported = ["ct_bri_steps", "ct_mired_steps", "hs_bri_steps", "hs_hue_steps", "hs_sat_steps", "effect_bri_steps", "measure_time_effect"];
    expect(unsupported.filter((name) => element.shadowRoot.querySelector(`input[name="${name}"]`))).toEqual([]);

    const light = element.shadowRoot.querySelector('select[name="light_entity_id"]') as HTMLSelectElement;
    light.value = "light.desk";
    light.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
  });

  it("auto-selects every supported color mode for a capable light", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.rgb", name: "RGB lamp", supported_modes: ["brightness", "color_temp", "hs"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toEqual(["brightness", "color_temp", "hs", "effect"]);
  });

  it("warns that an active light setup check controls the light and leaves it off", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.rgb", name: "RGB lamp", supported_modes: ["brightness", "hs"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("briefly controls the selected light");
    expect(element.shadowRoot.querySelector<HTMLButtonElement>('button[type="submit"]')?.textContent).toBe("Check light and setup");

    element.busy = true;
    await element.updateComplete;
    const progress = element.shadowRoot.querySelector('[role="status"]');
    expect(progress?.textContent).toContain("Checking low-load light settings");
    expect(progress?.textContent).toContain("representative low-load points");
    expect(progress?.querySelector("progress")?.hasAttribute("value")).toBe(false);

    element.busy = false;
    element.errorMessage = "The meter repeatedly returned 0 W.";
    element.errorHelp = {
      url: "https://docs.powercalc.nl/contributing/measure/low-power-measurements/",
      label: "Low-power measurement guide",
    };
    await element.updateComplete;
    const guide = element.shadowRoot.querySelector<HTMLAnchorElement>('[role="alert"] a');
    expect(guide?.textContent).toBe("Low-power measurement guide");
    expect(guide?.href).toBe("https://docs.powercalc.nl/contributing/measure/low-power-measurements/");
    expect(guide?.target).toBe("_blank");
    expect(guide?.rel).toBe("noopener noreferrer");
  });

  it("submits mode-specific native light-grid steps", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.rgb", name: "RGB lamp", supported_modes: ["brightness", "color_temp", "hs"] }];
    element.powers = [{
      entity_id: "sensor.plug_power",
      name: "Plug power",
      unit: "W",
      related_voltage_entity_id: "sensor.plug_voltage",
    }];
    element.voltages = [{ entity_id: "sensor.plug_voltage", name: "Plug voltage", unit: "V" }];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.selectedEntities = { light_entity_id: ["light.rgb"] };
    element.defaultPowerEntityId = "sensor.plug_power";
    element.defaultMeasureDevice = "Shelly Plug S";
    document.body.append(element);
    await element.updateComplete;

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_load"]')!.click();
    await element.updateComplete;
    element.shadowRoot.querySelector<HTMLInputElement>('input[name="dummy_load_description"]')!.value = "Incandescent reference load";
    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value = "LCT010";
    (element.shadowRoot.querySelector('input[name="product_name"]') as HTMLInputElement).value = "Test light";
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    const request = await submitted;
    expect(request.measure_type).toBe("light");
    expect(request.measure_device).toBe("Shelly Plug S");
    expect(request.dummy_load).toEqual({ mode: "calibrate", description: "Incandescent reference load" });
    expect(request.parameters).toMatchObject({
      bri_bri_steps: 1,
      ct_bri_steps: 5,
      ct_mired_steps: 10,
      hs_bri_steps: 32,
      hs_hue_steps: 2731,
      hs_sat_steps: 32,
    });
  });

  it("submits multiple lights, intersects their modes, and infers model and count", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [
      {
        entity_id: "light.one",
        name: "One group",
        model_id: "LWA017",
        supported_modes: ["brightness", "hs"],
        member_entity_ids: ["light.member_one", "light.member_two"],
      },
      { entity_id: "light.two", name: "Two", model_id: "LWA017", supported_modes: ["brightness"] },
      { entity_id: "light.member_one", name: "Member one", model_id: "LWA017", supported_modes: ["brightness"] },
      { entity_id: "light.member_two", name: "Member two", model_id: "LWA017", supported_modes: ["brightness"] },
    ];
    element.powers = [{ entity_id: "sensor.power", name: "Power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.selectedEntities = { light_entity_id: ["light.one", "light.two"] };
    element.multipleLights = true;
    element.defaultPowerEntityId = "sensor.power";
    element.defaultMeasureDevice = "Meter";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelectorAll('select[name="light_entity_id"]')).toHaveLength(2);
    const removeButton = element.shadowRoot.querySelector<HTMLButtonElement>("button.remove-entity");
    expect(removeButton?.getAttribute("aria-label")).toBe("Remove Light");
    expect(removeButton?.querySelector("svg")).toBeTruthy();
    expect(removeButton?.textContent?.trim()).toBe("");
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
    expect((element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value).toBe("LWA017");
    expect((element.shadowRoot.querySelector('input[name="multiple_light_count"]') as HTMLInputElement).value).toBe("2");

    (element.shadowRoot.querySelector('input[name="product_name"]') as HTMLInputElement).value = "Two identical lights";
    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );

    const request = await submitted;
    const lightRequest = request as Extract<MeasurementRequest, { measure_type: "light" }>;
    expect(lightRequest.controller).toEqual({ type: "hass_multi", entity_ids: ["light.one", "light.two"] });
    expect(lightRequest.multiple_light_count).toBe(2);
  });

  it("keeps multi-light controls hidden until the user opts in", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.power", name: "Power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".add-entity")).toBeNull();
    expect(element.shadowRoot.querySelector('input[name="multiple_light_count"][type="number"]')).toBeNull();
    expect(element.shadowRoot.querySelectorAll('select[name="light_entity_id"]')).toHaveLength(1);
    expect(element.shadowRoot.querySelector(".multiple-lights")?.textContent).toContain("very low power use");

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="measure_multiple_lights"]')!.click();
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".add-entity")).not.toBeNull();
    expect(element.shadowRoot.querySelector('input[name="multiple_light_count"][type="number"]')).not.toBeNull();
    const helpLink = element.shadowRoot.querySelector<HTMLAnchorElement>(".multiple-lights .help-link");
    expect(helpLink?.href).toBe("https://docs.powercalc.nl/contributing/measure/lights/#multiple-identical-lights");
    expect(helpLink?.getAttribute("aria-label")).toBe("Learn more about measuring multiple identical lights");
    expect(helpLink?.querySelector("svg")).toBeTruthy();
  });

  it("hides the virtual-device toggle unless developer mode is enabled", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('input[name="use_dummy_controller"]')).toBeNull();
  });

  it("submits a dummy light controller when the developer virtual-device toggle is on", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = { ...capabilities, developer_mode: true };
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.defaultMeasureDevice = "Shelly Plug S";
    document.body.append(element);
    await element.updateComplete;

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_controller"]')!.click();
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="light_entity_id"]')).toBeNull();
    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toEqual(["brightness", "color_temp", "hs", "effect"]);

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value = "dummy";
    (element.shadowRoot.querySelector('input[name="product_name"]') as HTMLInputElement).value = "Virtual light";
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    const request = await submitted;
    expect(request.measure_type).toBe("light");
    expect("controller" in request && request.controller).toEqual({ type: "dummy" });
  });

  it("submits a dummy fan controller when the developer virtual-device toggle is on", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan",
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }], label: "Fan", description: "Measure fan power.",
      fields: [{ name: "fan_entity_id", role: "controller", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      supports_profile: true, supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [fanDefinition];
    element.capabilities = { ...capabilities, developer_mode: true };
    element.powerMeter = "dummy";
    element.deviceEntities = {};
    element.selectedType = "fan";
    document.body.append(element);
    await element.updateComplete;

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_controller"]')!.click();
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="fan_entity_id"]')).toBeNull();

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value = "dummy";
    (element.shadowRoot.querySelector('input[name="product_name"]') as HTMLInputElement).value = "Virtual fan";
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    const request = await submitted;
    expect(request.measure_type).toBe("fan");
    expect("controller" in request && request.controller).toEqual({ type: "dummy" });
  });

  it("includes effect mode when the light exposes effects", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.effect", name: "Effect lamp", supported_modes: ["brightness", "effect"], effect_list: ["colorloop"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const labels = [...element.shadowRoot.querySelectorAll("label.check")].map((label) => label.textContent?.trim());
    expect(labels).toContain("Effect");
    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toContain("effect");
    const parameter = (name: string) => element.shadowRoot.querySelector<HTMLInputElement>(`input[name="${name}"]`);
    expect(parameter("effect_bri_steps")).toBeTruthy();
    expect(parameter("measure_time_effect")).toBeTruthy();

    const effect = element.shadowRoot.querySelector<HTMLInputElement>('input[name="modes"][value="effect"]');
    if (!effect) throw new Error("Expected effect mode input");
    effect.checked = false;
    effect.dispatchEvent(new Event("change"));
    // Deselecting a mode re-renders from state rather than mutating the DOM in place.
    await element.updateComplete;
    // Every mode's parameters disappear with it, so none of them can be submitted by accident.
    expect(parameter("effect_bri_steps")).toBeNull();
    expect(parameter("measure_time_effect")).toBeNull();
    expect(parameter("bri_bri_steps")).toBeTruthy();
  });
});

const definitions: MeasureDefinition[] = [
  lightDefinition,
  {
    measure_type: "average",
        icon: "📊",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }],
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

describe("setup type picker", () => {
  it("uses a matching saved dummy-load calibration by default", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.powers = [{
      entity_id: "sensor.plug_power",
      name: "Plug power",
      unit: "W",
      related_voltage_entity_id: "sensor.plug_voltage",
    }];
    element.powerMeter = "hass";
    element.defaultPowerEntityId = "sensor.plug_power";
    element.defaultMeasureDevice = "Shelly Plug S";
    element.selectedType = "average";
    element.dummyLoadCalibration = {
      description: "60 W incandescent bulb",
      resistance: 882.4,
      calibrated_at: "2026-07-16T10:00:00Z",
    };
    document.body.append(element);
    await element.updateComplete;

    const enabled = element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_load"]');
    expect(enabled).toBeTruthy();
    enabled!.click();
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("60 W incandescent bulb");
    expect(element.shadowRoot.textContent).toContain("882.4 Ω");
    expect(element.shadowRoot.textContent).toContain("Use saved calibration");
    expect(element.shadowRoot.textContent).toContain("Recalibrate");

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await submitted).dummy_load).toEqual({
      mode: "reuse",
      description: "60 W incandescent bulb",
      resistance: 882.4,
    });
  });

  it("collects a load description when inline calibration is required", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.powerMeter = "shelly";
    element.selectedType = "average";
    element.dummyLoadCalibration = null;
    document.body.append(element);
    await element.updateComplete;

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_load"]')!.click();
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("at least 10 minutes");
    const description = element.shadowRoot.querySelector<HTMLInputElement>('input[name="dummy_load_description"]');
    expect(description?.required).toBe(true);
    description!.value = "Ceramic heater";

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await submitted).dummy_load).toEqual({ mode: "calibrate", description: "Ceramic heater" });
  });

  it("does not offer a resistive dummy load for the synthetic test meter", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.powerMeter = "dummy";
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('input[name="use_dummy_load"]')).toBeNull();
    expect(element.shadowRoot.textContent).toContain("Synthetic test meter");
  });

  it("disables a resistive dummy load when the Home Assistant meter has no voltage sensor", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.powerMeter = "hass";
    element.defaultPowerEntityId = "sensor.plug_power";
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_load"]')?.disabled).toBe(true);
    expect(element.shadowRoot.textContent).toContain("requires a voltage sensor");
  });

  it("requires power meter setup before choosing a measurement type", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.powerMeterConfigured = false;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Set up your power meter");
    expect(element.shadowRoot.querySelector(".type-card")).toBeNull();
    const openSettings = new Promise<void>((resolve) => element.addEventListener("open-settings", () => resolve()));
    (element.shadowRoot.querySelector(".power-meter-required button") as HTMLButtonElement).click();
    await openSettings;
  });

  it("shows a card per measurement type before a type is chosen", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelectorAll(".type-card")).toHaveLength(2);
    expect(element.shadowRoot.textContent).toContain("Measure average power for a fixed duration.");
    expect(element.shadowRoot.querySelector("form")).toBeNull();
  });

  it("renders generic fields, dedupes the power sensor, and emits one typed preflight request", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.powerMeter = "hass";
    element.defaultPowerEntityId = "sensor.plug_power";
    element.defaultMeasureDevice = "Shelly Plug S";
    element.capabilities = capabilities;
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="power_entity_id"]')).toBeNull();
    expect(element.shadowRoot.querySelector(".power-meter-summary")?.textContent).toContain("Plug power · sensor.plug_power");
    expect(element.shadowRoot.querySelector(".power-meter-summary button")?.textContent).toContain("Change");
    expect(element.shadowRoot.querySelector('input[name="duration"]')).toBeTruthy();
    const readingInterval = element.shadowRoot.querySelector('input[name="sleep_time"]') as HTMLInputElement;
    expect(readingInterval).toBeTruthy();
    expect(element.shadowRoot.querySelector('input[name="sample_count"]')).toBeNull();
    readingInterval.value = "2.5";
    // The powermeter field from the definition must not be rendered a second time.
    expect(element.shadowRoot.querySelectorAll('[name="powermeter_entity_id"]')).toHaveLength(0);

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();
    const request = await submitted;
    expect(request.measure_type).toBe("average");
    expect(request.measure_device).toBe("Shelly Plug S");
    expect(request.power_meter).toEqual({ type: "hass", entity_id: "sensor.plug_power", voltage_entity_id: null });
    expect(request.measure_type === "average" && request.duration).toBe(60);
    expect(request.parameters.sleep_time).toBe(2.5);
    expect(request.parameters.sample_count).toBe(capabilities.defaults.sample_count);
  });

  it("includes the configured Shelly adapter in the submitted request", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.powerMeter = "shelly";
    element.shellyIp = "192.0.2.20";
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await submitted).power_meter).toEqual({ type: "shelly", device_ip: "192.0.2.20", username: "admin" });
  });

  it("includes the configured Kasa adapter in the submitted request", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.powerMeter = "kasa";
    element.kasaIp = "192.0.2.30";
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await submitted).power_meter).toEqual({ type: "kasa", device_ip: "192.0.2.30" });
  });

  it("renders an entity dropdown for a device domain when entities are available", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan",
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }],
      label: "Fan",
      description: "Measure fan power across percentage levels.",
      fields: [
        { name: "power_entity_id", role: "power_meter", label: "Power sensor", control: "entity", required: true, options: [] },
        { name: "fan_entity_id", role: "controller", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] },
      ],
      supports_profile: true,
      supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [fanDefinition];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.powerMeter = "hass";
    element.deviceEntities = { fan: [{ entity_id: "fan.bedroom", name: "Bedroom fan" }] };
    element.capabilities = capabilities;
    element.selectedType = "fan";
    document.body.append(element);
    await element.updateComplete;

    const fanSelect = element.shadowRoot.querySelector('select[name="fan_entity_id"]') as HTMLSelectElement;
    expect(fanSelect).toBeTruthy();
    expect(fanSelect.textContent).toContain("Bedroom fan · fan.bedroom");
  });

  it.each([
    {
      type: "fan" as const,
      definition: {
        measure_type: "fan" as const,
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }],
        label: "Fan",
        description: "Measure fan power across percentage levels.",
        fields: [
          { name: "fan_entity_id", role: "controller" as const, label: "Fan", control: "entity" as const, required: true, entity_domains: ["fan"], options: [] },
        ],
        supports_profile: true,
        supports_resume: false,
      },
      entities: { fan: [{ entity_id: "fan.bedroom", name: "Bedroom fan", model_id: "FAN-001" }] },
      entityField: "fan_entity_id",
      entityId: "fan.bedroom",
      expectedFields: ["fan_entity_id", "model_id", "product_name"],
      modelId: "FAN-001",
    },
    {
      type: "speaker" as const,
      definition: {
        measure_type: "speaker" as const,
        icon: "🔊",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }],
        label: "Speaker",
        description: "Measure power across media-player volume levels.",
        fields: [
          { name: "media_player_entity_id", role: "controller" as const, label: "Media player", control: "entity" as const, required: true, entity_domains: ["media_player"], options: [] },
          { name: "disable_streaming", role: "attribute" as const, label: "Disable automatic pink-noise streaming", control: "boolean" as const, required: false, default: false, options: [] },
        ],
        supports_profile: true,
        supports_resume: false,
      },
      entities: { media_player: [{ entity_id: "media_player.office", name: "Office speaker", model_id: "SPEAKER-001" }] },
      entityField: "media_player_entity_id",
      entityId: "media_player.office",
      expectedFields: ["media_player_entity_id", "disable_streaming", "model_id", "product_name"],
      modelId: "SPEAKER-001",
    },
    {
      type: "charging" as const,
      definition: {
        measure_type: "charging" as const,
        icon: "🔋",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }, { name: "sample_count", label: "Samples per reading", hint: "More samples reduce noise but increase measurement time.", group: "Sampling" }, { name: "sleep_time_sample", label: "Time between samples (seconds)", hint: "Only used when taking more than one sample.", group: "Sampling", requires_multiple: "sample_count" }],
        label: "Charging device",
        description: "Measure charging power against battery level.",
        fields: [
          {
            name: "charging_device_type",
            role: "attribute" as const,
            label: "Charging device type",
            control: "select" as const,
            required: true,
            options: [
              { value: "vacuum_robot", label: "Vacuum robot", entity_domain: "vacuum" },
              { value: "lawn_mower_robot", label: "Lawn mower robot", entity_domain: "lawn_mower" },
            ],
          },
          {
            name: "charging_entity_id",
            role: "controller" as const,
            narrowed_by: "charging_device_type",
            label: "Charging device",
            control: "entity" as const,
            required: true,
            entity_domains: ["vacuum", "lawn_mower"],
            options: [],
          },
        ],
        supports_profile: true,
        supports_resume: false,
      },
      entities: { vacuum: [{ entity_id: "vacuum.downstairs", name: "Downstairs vacuum", model_id: "VAC-001" }] },
      entityField: "charging_entity_id",
      entityId: "vacuum.downstairs",
      expectedFields: ["charging_device_type", "charging_entity_id", "model_id", "product_name"],
      modelId: "VAC-001",
    },
  ])("orders $type fields by dependency and prefills the selected device model ID", async ({
    type, definition, entities, entityField, entityId, expectedFields, modelId,
  }) => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [definition];
    element.capabilities = capabilities;
    element.powerMeter = "dummy";
    element.deviceEntities = Object.fromEntries(Object.entries(entities));
    element.selectedType = type;
    document.body.append(element);
    await element.updateComplete;

    const profileSection = [...element.shadowRoot.querySelectorAll("fieldset.section")][1];
    // Query from the profile grid directly instead of using a `:scope >` selector.
    // jsdom's selector engine does not resolve `:scope` against a context node that
    // lives inside a shadow root, so those selectors match nothing under the app's
    // shadow DOM even though browsers resolve them fine.
    const profileGrid = profileSection?.querySelector(".profile-grid");
    const fields = [...(profileGrid?.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[name]") ?? [])];
    expect(fields.map((field) => field.name)).toEqual(expectedFields);

    const entity = element.shadowRoot.querySelector(`select[name="${entityField}"]`) as HTMLSelectElement;
    entity.value = entityId;
    entity.dispatchEvent(new Event("change"));
    await element.updateComplete;

    expect((element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value).toBe(modelId);
  });

  it("shows entity discovery failures instead of silently enabling free-text input", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan",
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }], label: "Fan", description: "Measure fan power.",
      fields: [{ name: "fan_entity_id", role: "controller", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      supports_profile: false, supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [fanDefinition];
    element.capabilities = capabilities;
    element.powerMeter = "dummy";
    element.deviceEntityErrors = { fan: "Home Assistant is unavailable" };
    element.selectedType = "fan";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".notice.error")?.textContent).toContain("Home Assistant is unavailable");
    expect(element.shadowRoot.querySelector('[name="fan_entity_id"]')).toBeNull();
  });

  it("filters charging entities by the selected device type", async () => {
    const chargingDefinition: MeasureDefinition = {
      measure_type: "charging",
        icon: "🔋",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }, { name: "sample_count", label: "Samples per reading", hint: "More samples reduce noise but increase measurement time.", group: "Sampling" }, { name: "sleep_time_sample", label: "Time between samples (seconds)", hint: "Only used when taking more than one sample.", group: "Sampling", requires_multiple: "sample_count" }], label: "Charging device", description: "Measure charging power.",
      fields: [
        {
          name: "charging_device_type", role: "attribute", label: "Device type", control: "select", required: true,
          options: [
            { value: "vacuum_robot", label: "Vacuum", entity_domain: "vacuum" },
            { value: "lawn_mower_robot", label: "Lawn mower", entity_domain: "lawn_mower" },
          ],
        },
        {
          name: "charging_entity_id", role: "controller", narrowed_by: "charging_device_type", label: "Charging device", control: "entity", required: true,
          entity_domains: ["vacuum", "lawn_mower"], options: [],
        },
      ],
      supports_profile: false, supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [chargingDefinition];
    element.capabilities = capabilities;
    element.powerMeter = "dummy";
    element.deviceEntities = {
      vacuum: [{ entity_id: "vacuum.downstairs", name: "Downstairs vacuum" }],
      lawn_mower: [{ entity_id: "lawn_mower.garden", name: "Garden mower" }],
    };
    element.selectedType = "charging";
    document.body.append(element);
    await element.updateComplete;

    const entity = element.shadowRoot.querySelector('[name="charging_entity_id"]') as HTMLSelectElement;
    expect(entity.textContent).toContain("Downstairs vacuum");
    expect(entity.textContent).not.toContain("Garden mower");

    const type = element.shadowRoot.querySelector('[name="charging_device_type"]') as HTMLSelectElement;
    type.value = "lawn_mower_robot";
    type.dispatchEvent(new Event("change"));
    await element.updateComplete;

    const updated = element.shadowRoot.querySelector('[name="charging_entity_id"]') as HTMLSelectElement;
    expect(updated.textContent).toContain("Garden mower");
    expect(updated.textContent).not.toContain("Downstairs vacuum");
  });
});

describe("running view", () => {
  it("shows an indeterminate preparation state instead of zero progress", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", phase: "Preparing measurement devices" };
    document.body.append(element);
    await element.updateComplete;

    const preparation = element.shadowRoot.querySelector(".preparation");
    expect(preparation?.getAttribute("role")).toBe("status");
    expect(preparation?.getAttribute("aria-live")).toBe("polite");
    expect(preparation?.textContent).toContain("Preparing measurement devices");
    expect(element.shadowRoot.querySelector("#running-title")?.textContent).toBe("Preparing measurement");
    expect(element.shadowRoot.querySelector(".preparation-spinner")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".preparation-bar")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".value")).toBeNull();
    expect(element.shadowRoot.querySelector("progress")).toBeNull();
  });

  it("shows a dedicated ready card with the requested confirmation action", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; confirmationAction: string; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "awaiting_confirmation",
      confirmation_message: "Switch on the test signal, then start recording.",
    };
    element.confirmationAction = "Start recording";
    document.body.append(element);
    await element.updateComplete;

    const ready = element.shadowRoot.querySelector(".ready-card");
    const announcement = element.shadowRoot.querySelector(".ready-announcement");
    expect(announcement).toBeTruthy();
    expect(announcement?.getAttribute("role")).toBe("status");
    expect(announcement?.getAttribute("aria-live")).toBe("polite");
    expect(ready?.textContent).toContain("Switch on the test signal, then start recording.");
    expect(ready?.querySelector("button.confirm")?.textContent).toBe("Start recording");
    expect(element.shadowRoot.querySelector(".instrument")).toBeNull();
    expect(element.shadowRoot.querySelector("progress")).toBeNull();
  });

  it("renders speaker confirmation as a high-volume warning", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; confirmationAction: string; warningConfirmation: boolean;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "awaiting_confirmation",
      confirmation_message: "Speaker measurements can become very loud.",
    };
    element.confirmationAction = "Start speaker measurement";
    element.warningConfirmation = true;
    document.body.append(element);
    await element.updateComplete;

    const warning = element.shadowRoot.querySelector(".ready-card.warning");
    expect(warning).toBeTruthy();
    expect(warning?.querySelector(".ready-announcement")?.getAttribute("role")).toBe("alert");
    expect(warning?.textContent).toContain("High volume warning");
    expect(warning?.textContent).toContain("Protect your hearing");
    expect(warning?.querySelector(".ready-icon svg")).toBeTruthy();
  });

  it("shows progress, phase, connection state, and cancellation", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      connected: boolean;
      diagnosticsUrl: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", phase: "Brightness", mode: "brightness", progress: { completed: 25, total: 100, estimated_remaining_seconds: 120 } };
    element.connected = true;
    element.diagnosticsUrl = "http://ha.local/ingress/api/session/current/diagnostics";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("25%");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.textContent).toContain("Live");
    expect(element.shadowRoot.querySelector("progress")?.value).toBe(25);
    expect(element.shadowRoot.querySelector("button")?.textContent).toContain("Cancel measurement");
    const diagnostics = element.shadowRoot.querySelector(".diagnostics-download a") as HTMLAnchorElement;
    expect(diagnostics.textContent).toBe("Download diagnostics");
    expect(diagnostics.href).toBe(element.diagnosticsUrl);
    expect(element.shadowRoot.querySelector(".diagnostics-download")?.textContent).toContain("snapshot and logs");
  });

  it("shows sub-one-percent progress and skipped readings", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", mode: "brightness", progress: { completed: 1, total: 300, skipped: 1 } };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".value")?.textContent).toContain("<1%");
    expect(element.shadowRoot.querySelector("progress")?.value).toBeCloseTo(1 / 300 * 100);
    expect(element.shadowRoot.textContent).toContain("1 / 300");
    expect(element.shadowRoot.textContent).toContain("Skipped");
  });

  it("draws a live power chart from streamed samples", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; samples: number[]; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", progress: { completed: 1, total: 10 } };
    element.samples = [4.2, 5.1, 4.8];
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".chart")).toBeTruthy();
    expect(element.shadowRoot.querySelector("svg.spark polyline.line")?.getAttribute("points")).toContain(",");
    expect(element.shadowRoot.querySelector(".chart-head strong")?.textContent).toContain("4.8");
    expect(element.shadowRoot.querySelector(".chart-scale")?.textContent).toContain("peak 5.1 W");
  });

  it("keeps live samples visible while numeric progress is not available yet", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; samples: number[]; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", phase: "Stabilizing device" };
    element.samples = [4.2, 4.3];
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".preparation")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".chart")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".value")).toBeNull();
  });

  it.each([
    [
      { type: "light", on: true, brightness: 128, color_temp_mired: 370, hue: 32_768, saturation: 128 } as OperatingPoint,
      ["Brightness 50%", "Color temp 2703 K", "Hue 180°", "Saturation 50%"],
    ],
    [{ type: "light", on: false } as OperatingPoint, ["Off"]],
    [{ type: "speaker", volume: 40, muted: false } as OperatingPoint, ["Volume 40%"]],
    [{ type: "speaker", volume: 0, muted: true } as OperatingPoint, ["Muted"]],
    [{ type: "fan", percentage: 65, on: true } as OperatingPoint, ["Fan speed 65%"]],
    [{ type: "charging", battery_level: 72, charging: true } as OperatingPoint, ["Battery 72%", "Charging"]],
  ])("renders a compact current measurement point for %#", async (operatingPoint, expected) => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", operating_point: operatingPoint };
    document.body.append(element);
    await element.updateComplete;

    const state = element.shadowRoot.querySelector(".operating-point");
    expect(element.shadowRoot.querySelector(".preparation")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".value")).toBeNull();
    expect(state?.getAttribute("aria-live")).toBe("polite");
    expect(state?.textContent).toContain("Current measurement point");
    for (const value of expected) expect(state?.textContent).toContain(value);
  });

  it.each([
    [
      { type: "light", on: true, brightness: 128, color_temp_mired: 370, hue: 32_768, saturation: 128, effect: "candle" } as OperatingPoint,
      ["brightness", "color-temp", "hue", "saturation", "effect"],
    ],
    [{ type: "light", on: false } as OperatingPoint, ["off"]],
    [{ type: "speaker", volume: 40, muted: false } as OperatingPoint, ["volume"]],
    [{ type: "speaker", volume: 0, muted: true } as OperatingPoint, ["muted"]],
    [{ type: "fan", percentage: 65, on: true } as OperatingPoint, ["fan-speed"]],
    [{ type: "fan", percentage: 0, on: false } as OperatingPoint, ["off"]],
    [{ type: "charging", battery_level: 72, charging: true } as OperatingPoint, ["battery", "charging"]],
    [{ type: "charging", battery_level: 25, charging: false } as OperatingPoint, ["battery", "not-charging"]],
  ])("adds an icon to every operating-point chip for %#", async (operatingPoint, icons) => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", operating_point: operatingPoint };
    document.body.append(element);
    await element.updateComplete;

    const chips = [...element.shadowRoot.querySelectorAll(".state-chip")];
    const renderedIcons = [...element.shadowRoot.querySelectorAll("[data-state-icon]")];
    expect(renderedIcons.map((icon) => icon.getAttribute("data-state-icon"))).toEqual(icons);
    expect(renderedIcons).toHaveLength(chips.length);
    for (const icon of renderedIcons) expect(icon.getAttribute("aria-hidden")).toBe("true");
  });

  it("hides the power chart until the first sample arrives", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "awaiting_confirmation" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".chart")).toBeNull();
  });

  it("shows a live sample count for an open-ended recording", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", mode: "Recording", progress: { completed: 7, total: 0 } };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".value")?.textContent).toContain("7");
    expect(element.shadowRoot.textContent).toContain("samples");
    expect(element.shadowRoot.textContent).toContain("Until stopped");
    const stop = [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Stop recording"));
    expect(stop).toBeTruthy();
    expect(element.shadowRoot.querySelector("button.danger")).toBeNull();
  });

  it("labels average progress in seconds", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", mode: "Averaging", progress: { completed: 12, total: 60, estimated_remaining_seconds: 48 } };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Seconds");
    expect(element.shadowRoot.textContent).toContain("12 / 60");
  });

  it("keeps the log collapsed by default and opens it as an overlay on toggle", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; logs: string[]; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", progress: { completed: 1, total: 10 } };
    element.logs = ["First log", "Second log"];
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".log-overlay")).toBeNull();
    const toggle = element.shadowRoot.querySelector(".log-toggle") as HTMLButtonElement;
    expect(toggle.textContent).toContain("View log");
    expect(toggle.textContent).toContain("2");

    toggle.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".log-overlay")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".log-overlay")?.textContent).toContain("Second log");
  });

  it("presents discarded readings as warnings in the page and log panel", async () => {
    const warning = "Discarding measurement: 0 watt was read from the power meter";
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; logs: string[]; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", progress: { completed: 0, total: 2 }, warnings: [warning] };
    element.logs = [warning];
    document.body.append(element);
    await element.updateComplete;

    const notice = element.shadowRoot.querySelector(".notice.warning");
    expect(notice?.getAttribute("role")).toBe("alert");
    expect(notice?.textContent).toContain(warning);

    (element.shadowRoot.querySelector(".log-toggle") as HTMLButtonElement).click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".log p.warning")?.textContent).toContain(warning);
  });

  it("auto-scrolls the log container when new log lines arrive", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      connected: boolean;
      logs: string[];
      logOpen: boolean;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", progress: { completed: 1, total: 10 } };
    element.logs = ["First log"];
    element.logOpen = true;
    document.body.append(element);
    await element.updateComplete;

    const logContainer = element.shadowRoot.querySelector(".log") as HTMLDivElement;
    Object.defineProperty(logContainer, "scrollHeight", { value: 240, configurable: true });
    Object.defineProperty(logContainer, "scrollTop", { value: 0, writable: true, configurable: true });

    element.logs = [...element.logs, "Second log"];
    await element.updateComplete;

    expect(logContainer.scrollTop).toBe(240);
  });
});

describe("setup view defaults", () => {
  it("shows the configured power sensor as read-only measurement context", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.defaultPowerEntityId = "sensor.plug_power";
    element.defaultMeasureDevice = "Shelly Plug S";
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="power_entity_id"]')).toBeNull();
    expect(element.shadowRoot.querySelector('input[name="measure_device"]')).toBeNull();
    expect(element.shadowRoot.querySelector(".power-meter-summary")?.textContent).toContain("Plug power · sensor.plug_power");
    expect(element.shadowRoot.querySelector(".power-meter-summary")?.textContent).toContain("Measurement device: Shelly Plug S");
    const openSettings = new Promise<void>((resolve) => element.addEventListener("open-settings", () => resolve()));
    (element.shadowRoot.querySelector(".power-meter-summary button") as HTMLButtonElement).click();
    await openSettings;
  });

  it("shows the voltage sensor automatically paired with the configured power sensor", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [
      { entity_id: "sensor.plug_power", name: "Plug power", unit: "W", related_voltage_entity_id: "sensor.plug_line_voltage" },
      { entity_id: "sensor.strip_consumption", name: "Strip power", unit: "W", related_voltage_entity_id: "sensor.strip_mains" },
    ];
    element.voltages = [
      { entity_id: "sensor.plug_line_voltage", name: "Plug voltage", unit: "V", device_id: "plug-device" },
      { entity_id: "sensor.strip_mains", name: "Strip voltage", unit: "V", device_id: "strip-device" },
    ];
    element.defaultPowerEntityId = "sensor.plug_power";
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const summary = element.shadowRoot.querySelector(".power-meter-summary");
    expect(summary?.textContent).toContain("Plug power · sensor.plug_power");
    expect(summary?.textContent).toContain("Voltage: Plug voltage · sensor.plug_line_voltage");
    expect(element.shadowRoot.querySelector('select[name="voltage_entity_id"]')).toBeNull();
  });

  it("prefills the model ID from the selected measurement device", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"], device_id: "light-device", model_id: "LWA017" }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", device_id: "plug-device", model_id: "WSP002" }];
    element.voltages = [];
    element.defaultPowerEntityId = "sensor.plug_power";
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const light = element.shadowRoot.querySelector('select[name="light_entity_id"]') as HTMLSelectElement;
    light.value = "light.desk";
    light.dispatchEvent(new Event("change"));
    await element.updateComplete;

    const modelId = element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement;
    expect(modelId.value).toBe("LWA017");
  });

  it("orders the light fields by dependency and explains the full product name", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const profileSection = [...element.shadowRoot.querySelectorAll("fieldset.section")][1];
    expect(profileSection).toBeTruthy();
    const profileGrid = profileSection?.querySelector(".profile-grid");
    expect(profileGrid).toBeTruthy();
    // Walk the grid's direct children rather than using `:scope >` selectors, which
    // jsdom cannot resolve against a context node inside a shadow root. This keeps
    // the assertion scoped to the profile fields and excludes the nested advanced
    // timing grid, exactly as the `:scope > .grid > label` selector intended.
    const profileFields = [...(profileGrid?.children ?? [])].filter(
      (child): child is HTMLLabelElement => child.tagName === "LABEL",
    );
    const labels = profileFields.map(
      (field) => [...field.children].find((child) => child.tagName === "SPAN")?.textContent?.trim(),
    );
    expect(labels).toEqual(["Light"]);
    expect([...element.shadowRoot.querySelectorAll(".profile-fields > label > span")].map((label) => label.textContent?.trim()))
      .toEqual(["Model ID", "Full product name"]);
    expect(element.shadowRoot.querySelector(".field-hint")?.textContent).toContain("complete marketed name");
  });
});

describe("settings view", () => {
  it("lists power sensors and emits the selected default on save", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[];
      settings: AppSettings;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.settings = defaultSettings;
    document.body.append(element);
    await element.updateComplete;

    const sectionButtons = [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".settings-nav button")];
    expect(sectionButtons.map((button) => button.textContent?.trim())).toEqual(["Power meter", "Measure tuning", "GitHub"]);
    expect(sectionButtons[0]?.classList.contains("active")).toBe(true);
    expect(element.shadowRoot.querySelector<HTMLElement>('[aria-labelledby="measure-tuning-title"]')?.hidden).toBe(true);

    sectionButtons[1]?.click();
    await element.updateComplete;
    expect(sectionButtons[1]?.classList.contains("active")).toBe(true);
    expect(element.shadowRoot.querySelector<HTMLElement>('[aria-labelledby="power-meter-title"]')?.hidden).toBe(true);
    expect(element.shadowRoot.querySelector<HTMLElement>('[aria-labelledby="measure-tuning-title"]')?.hidden).toBe(false);

    const saved = new Promise<AppSettings>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    const select = element.shadowRoot.querySelector('select[name="default_power_entity_id"]') as HTMLSelectElement;
    const measureDevice = element.shadowRoot.querySelector('input[name="default_measure_device"]') as HTMLInputElement;
    expect(measureDevice.required).toBe(true);
    measureDevice.value = "Shelly Plug S";
    expect(select.required).toBe(true);
    expect(select.options[0]?.textContent).toBe("Select a power sensor");
    select.value = "sensor.plug_power";
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    const settings = await saved;
    expect(settings.default_power_entity_id).toBe("sensor.plug_power");
    expect(settings.measurement_defaults).toEqual(measurementDefaults);
  });

  it("shows fast test mode only in developer mode and saves the toggle", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      settings: AppSettings;
      capabilities: Capabilities;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.settings = {
      ...defaultSettings,
      default_measure_device: "Synthetic meter",
      power_meter: "dummy",
    };
    element.capabilities = capabilities;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('input[name="fast_test_mode"]')).toBeNull();

    element.capabilities = { ...capabilities, developer_mode: true };
    await element.updateComplete;
    const toggle = element.shadowRoot.querySelector('input[name="fast_test_mode"]') as HTMLInputElement;
    expect(toggle).not.toBeNull();
    expect(element.shadowRoot.textContent).toContain("output is not valid for contribution or real use");

    toggle.checked = true;
    const saved = new Promise<AppSettings>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await saved).fast_test_mode).toBe(true);
  });

  it("renders GitHub device login, token fallback, identity, and disconnect", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[];
      settings: AppSettings;
      contributionAuth: { connected: boolean; identity?: { login: string; name?: string } };
      contributionDeviceFlow: { flow_id: string; user_code: string; verification_uri: string; expires_in: number; interval: number };
      contributionDeviceStatus: { status: "pending" | "expired"; message?: string };
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = defaultSettings;
    element.contributionAuth = { connected: false };
    document.body.append(element);
    await element.updateComplete;

    [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".settings-nav button")].find((button) => button.textContent?.includes("GitHub"))?.click();
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Connect GitHub");
    expect(element.shadowRoot.textContent).toContain("Use a personal access token instead");
    expect(element.shadowRoot.textContent).toContain("included in Home Assistant backups");
    const started = new Promise<void>((resolve) => element.addEventListener("github-device-start", () => resolve()));
    [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Connect GitHub"))?.click();
    await started;

    element.contributionDeviceFlow = {
      flow_id: "flow-1",
      user_code: "ABCD-EFGH",
      verification_uri: "https://github.com/login/device",
      expires_in: 900,
      interval: 5,
    };
    await element.updateComplete;
    expect((element.shadowRoot.querySelector(".device-code") as HTMLInputElement).value).toBe("ABCD-EFGH");
    expect(element.shadowRoot.textContent).toContain("Continue on GitHub");
    expect(element.shadowRoot.textContent).toContain("connect automatically");
    expect(element.shadowRoot.textContent).not.toContain("Check login");
    expect((element.shadowRoot.querySelector(".github-link") as HTMLAnchorElement).href).toBe("https://github.com/login/device");

    [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Copy code"))?.click();
    await vi.waitFor(() => expect(element.shadowRoot.textContent).toContain("Select the code and copy it manually"));
    expect(element.shadowRoot.textContent).not.toContain("Code copied.");

    element.contributionDeviceStatus = { status: "expired", message: "This code expired." };
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("This code expired.");
    expect(element.shadowRoot.textContent).toContain("Get a new code");

    const saved = new Promise<string>((resolve) => element.addEventListener("github-token-save", (event) => resolve((event as CustomEvent<string>).detail)));
    const token = element.shadowRoot.querySelector('input[name="github_token"]') as HTMLInputElement;
    token.value = "ghp_secret";
    [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Save token"))?.click();
    expect(await saved).toBe("ghp_secret");

    element.contributionAuth = { connected: true, identity: { login: "octocat" } };
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("octocat");
    const disconnected = new Promise<void>((resolve) => element.addEventListener("github-disconnect", () => resolve()));
    (element.shadowRoot.querySelector("button.danger") as HTMLButtonElement).click();
    await disconnected;
  });

  it("copies the device code through execCommand when the clipboard API is unavailable", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      settings: AppSettings;
      contributionAuth: { connected: boolean };
      contributionDeviceFlow: { flow_id: string; user_code: string; verification_uri: string; expires_in: number; interval: number };
      initialSection: SettingsSection;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.settings = defaultSettings;
    element.contributionAuth = { connected: false };
    element.initialSection = "github";
    element.contributionDeviceFlow = {
      flow_id: "flow-1",
      user_code: "BA41-1016",
      verification_uri: "https://github.com/login/device",
      expires_in: 900,
      interval: 5,
    };
    document.body.append(element);
    await element.updateComplete;

    // Insecure context: navigator.clipboard is not exposed at all, as inside the http ingress panel.
    const clipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    let copied = "";
    const execCommand = vi.fn(() => {
      copied = document.querySelector("textarea")?.value ?? "";
      return true;
    });
    Object.defineProperty(document, "execCommand", { value: execCommand, configurable: true });

    const copyButton = [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Copy code"));
    copyButton?.click();
    await vi.waitFor(() => expect(element.shadowRoot.textContent).toContain("Code copied."));
    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(copied).toBe("BA41-1016");
    expect(document.querySelector("textarea")).toBeNull();

    // A rejecting clipboard API (blocked by permissions policy or an unfocused document) also falls back.
    const writeText = vi.fn().mockRejectedValue(new DOMException("Write permission denied.", "NotAllowedError"));
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    execCommand.mockClear();
    copyButton?.click();
    await vi.waitFor(() => expect(execCommand).toHaveBeenCalledWith("copy"));
    expect(writeText).toHaveBeenCalledWith("BA41-1016");

    if (clipboard) Object.defineProperty(navigator, "clipboard", clipboard);
  });

  it("opens directly on the GitHub section when a section is requested", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[];
      settings: AppSettings;
      contributionAuth: { connected: boolean };
      initialSection: SettingsSection;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = defaultSettings;
    element.contributionAuth = { connected: false };
    element.initialSection = "github";
    document.body.append(element);
    await element.updateComplete;

    const githubNav = [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".settings-nav button")]
      .find((button) => button.textContent?.includes("GitHub"));
    expect(githubNav?.getAttribute("aria-current")).toBe("page");
    const githubSection = element.shadowRoot.querySelector('[aria-labelledby="github-title"]');
    expect(githubSection?.hasAttribute("hidden")).toBe(false);
  });
});

describe("app shell device entities", () => {
  it("loads device entities only after their measurement type is selected", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan",
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }], label: "Fan", description: "Measure fan power across percentage levels.",
      fields: [
        { name: "power_entity_id", role: "power_meter", label: "Power sensor", control: "entity", required: true, options: [], entity_domains: ["sensor"] },
        { name: "fan_entity_id", role: "controller", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] },
      ],
      supports_profile: true, supports_resume: false,
    };
    const requestedDomains: string[] = [];
    const element = new AppShell();
    (element as unknown as { api: unknown }).api = {
      getCapabilities: async () => capabilities,
      getEntityCatalog: async () => ({ lights: [], powers: [], voltages: [] }),
      getEntitiesByDeviceClass: async () => [],
      getSettings: async () => defaultSettings,
      getContributionAuth: async () => ({ connected: false }),
      getDummyLoadCalibration: async () => null,
      getCurrent: async () => ({ state: "idle" }),
      getMeasureDefinitions: async () => [fanDefinition],
      getEntitiesByDomain: async (domain: string) => {
        requestedDomains.push(domain);
        return domain === "fan" ? [{ entity_id: "fan.bedroom", name: "Bedroom fan" }] : [];
      },
      getContributionDraft: async () => ({ eligible: false }),
    };

    await (element as unknown as { boot: () => Promise<void> }).boot();
    document.body.append(element);
    await element.updateComplete;

    expect(requestedDomains).toEqual([]);
    expect(element.shadowRoot?.querySelector(".version")?.textContent).toBe("Version v0.2.1");
    (element as unknown as { measureTypeSelected: (event: CustomEvent<"fan">) => void })
      .measureTypeSelected(new CustomEvent("measure-type-selected", { detail: "fan" }));
    await vi.waitFor(() => expect(element.deviceEntities.fan).toEqual([{ entity_id: "fan.bedroom", name: "Bedroom fan" }]));
    expect(requestedDomains).toEqual(["fan"]);
  });

  it("restores a generic request into the generic setup flow", async () => {
    const element = new AppShell();
    (element as unknown as { api: unknown }).api = {
      getCapabilities: async () => capabilities,
      getEntityCatalog: async () => ({ lights: [], powers: [], voltages: [] }),
      getEntitiesByDeviceClass: async () => [],
      getSettings: async () => defaultSettings,
      getContributionAuth: async () => ({ connected: false }),
      getDummyLoadCalibration: async () => null,
      getCurrent: async () => ({
        state: "idle",
        request: {
          measure_type: "average",
          model_id: "measurement",
          product_name: "Measurement",
          measure_device: "",
          power_meter: { type: "hass", entity_id: "sensor.plug_power" },
          duration: 60,
          generate_model: false,
          parameters: { ...capabilities.defaults, sleep_time: 2, sample_count: 1 },
          resume_policy: "new",
        },
      }),
      getMeasureDefinitions: async () => [],
      getEntitiesByDomain: async () => [],
      getContributionDraft: async () => ({ eligible: false }),
    };

    await (element as unknown as { boot: () => Promise<void> }).boot();

    expect(element.request?.measure_type).toBe("average");
  });
});

describe("settings power meter test", () => {
  it("explains the meter requirements, emits a validation event, and shows diagnostic metrics", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testResult: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.settings = { ...defaultSettings, default_power_entity_id: "sensor.plug_power" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("at least 0.1 W reported resolution");
    const tested = new Promise<AppSettings>((resolve) => {
      element.addEventListener("test", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    const testButton = [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Validate measurement device"));
    testButton?.click();
    const detail = await tested;
    expect(detail.power_meter).toBe("hass");
    expect(detail.default_power_entity_id).toBe("sensor.plug_power");

    element.testResult = goodPowerMeterDiagnostic;
    await element.updateComplete;
    const diagnostic = element.shadowRoot.querySelector("measure-power-meter-diagnostic") as HTMLElement & { updateComplete: Promise<boolean>; shadowRoot: ShadowRoot };
    await diagnostic.updateComplete;
    expect(diagnostic.shadowRoot.textContent).toContain("12.3 W");
    expect(diagnostic.shadowRoot.textContent).toContain("2 decimals");
    expect(diagnostic.shadowRoot.textContent).toContain("1.8 s");
    expect(diagnostic.shadowRoot.textContent).toContain("Good");
  });

  it("keeps the selected meter and Shelly IP across a re-render", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testing: boolean;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = defaultSettings;
    document.body.append(element);
    await element.updateComplete;

    const meterSelect = element.shadowRoot.querySelector('select[name="power_meter"]') as HTMLSelectElement;
    meterSelect.value = "shelly";
    meterSelect.dispatchEvent(new Event("change"));
    await element.updateComplete;
    (element.shadowRoot.querySelector('input[name="shelly_ip"]') as HTMLInputElement).value = "10.0.0.5";

    // Simulate an app-shell re-render (e.g. the test request toggling busy state).
    element.testing = true;
    await element.updateComplete;
    element.testing = false;
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('input[name="shelly_ip"]')).toBeTruthy();
    expect((element.shadowRoot.querySelector('input[name="shelly_ip"]') as HTMLInputElement).value).toBe("10.0.0.5");
  });

  it("collects the Kasa address without offering discovery", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testResult?: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = { ...defaultSettings, default_measure_device: "Kasa KP115" };
    element.testResult = goodPowerMeterDiagnostic;
    const discover = vi.fn();
    element.addEventListener("shelly-discover", discover);
    const saved = new Promise<AppSettings>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    document.body.append(element);
    await element.updateComplete;

    const meterSelect = element.shadowRoot.querySelector('select[name="power_meter"]') as HTMLSelectElement;
    meterSelect.value = "kasa";
    meterSelect.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect(discover).not.toHaveBeenCalled();
    // Selecting a direct meter invalidates the earlier Home Assistant sensor result.
    expect(element.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();
    expect(element.shadowRoot.querySelector('select[name="discovered_shelly"]')).toBeNull();

    const kasaIp = element.shadowRoot.querySelector('input[name="kasa_ip"]') as HTMLInputElement;
    kasaIp.value = "192.0.2.30";
    kasaIp.dispatchEvent(new Event("input"));
    await element.updateComplete;
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    const settings = await saved;
    expect(settings.power_meter).toBe("kasa");
    expect(settings.kasa_ip).toBe("192.0.2.30");
    expect(settings.shelly_ip).toBeNull();
  });

  it("discovers Shellys automatically and selects only compatible devices", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; shellyDiscoveryDevices: import("../types").ShellyDiscoveryDevice[];
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = defaultSettings;
    const discover = vi.fn();
    element.addEventListener("shelly-discover", discover);
    document.body.append(element);
    await element.updateComplete;

    const meterSelect = element.shadowRoot.querySelector('select[name="power_meter"]') as HTMLSelectElement;
    meterSelect.value = "shelly";
    meterSelect.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect(discover).toHaveBeenCalledOnce();

    element.shellyDiscoveryDevices = [
      { id: "plug", name: "Kitchen plug", model: "S3PL-00112EU", generation: 3, ip_address: "10.0.0.8", supported: true, reason: null, auth_required: false },
      { id: "auth", name: "Locked plug", model: null, generation: 2, ip_address: "10.0.0.9", supported: false, reason: "Authentication is enabled; enter the Shelly password.", auth_required: true },
    ];
    await element.updateComplete;

    const discovered = element.shadowRoot.querySelector('select[name="discovered_shelly"]') as HTMLSelectElement;
    expect(discovered.options[1]?.textContent).toContain("Kitchen plug");
    expect(discovered.options[2]?.textContent).toContain("Authentication is enabled");
    expect(discovered.options[2]?.disabled).toBe(false);
    discovered.value = "10.0.0.8";
    discovered.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect((element.shadowRoot.querySelector('input[name="shelly_ip"]') as HTMLInputElement).value).toBe("10.0.0.8");
  });

  it("submits Shelly credentials without losing a typed password on rerender", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      settings: AppSettings; testResult?: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.settings = {
      ...defaultSettings,
      default_measure_device: "Shelly Plug",
      power_meter: "shelly",
      shelly_ip: "10.0.0.9",
      shelly_username: "admin",
      shelly_password_configured: true,
    };
    document.body.append(element);
    await element.updateComplete;

    const username = element.shadowRoot.querySelector('input[name="shelly_username"]') as HTMLInputElement;
    const password = element.shadowRoot.querySelector('input[name="shelly_password"]') as HTMLInputElement;
    username.value = "measurement";
    username.dispatchEvent(new Event("input"));
    password.value = "device-password";
    password.dispatchEvent(new Event("input"));

    element.testResult = goodPowerMeterDiagnostic;
    await element.updateComplete;
    expect((element.shadowRoot.querySelector('input[name="shelly_password"]') as HTMLInputElement).value).toBe("device-password");

    const saved = new Promise<AppSettingsUpdate>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettingsUpdate>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect(await saved).toMatchObject({
      shelly_username: "measurement",
      shelly_password: "device-password",
      clear_shelly_password: false,
    });
  });

  it("renders Shelly discovery loading, empty, unavailable, and error states with refresh", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      settings: AppSettings; discoveringShellys: boolean; shellyDiscoveryAvailable?: boolean;
      shellyDiscoveryMessage?: string; shellyDiscoveryError: string;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.settings = { ...defaultSettings, power_meter: "shelly" };
    element.discoveringShellys = true;
    document.body.append(element);
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("Searching for Shelly devices");

    element.discoveringShellys = false;
    element.shellyDiscoveryAvailable = true;
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("No Shelly devices found");

    element.shellyDiscoveryAvailable = false;
    element.shellyDiscoveryMessage = "Discovery is unavailable.";
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("Discovery is unavailable.");

    element.shellyDiscoveryError = "Discovery request failed";
    await element.updateComplete;
    expect(element.shadowRoot.querySelector('[role="alert"]')?.textContent).toContain("Discovery request failed");
    expect([...element.shadowRoot.querySelectorAll("button")].some((button) => button.textContent?.includes("Refresh"))).toBe(true);
  });

  it("clears an earlier result when the power sensor, meter type, or Shelly address changes", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testResult?: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [
      { entity_id: "sensor.plug_power", name: "Plug power" },
      { entity_id: "sensor.other_power", name: "Other power" },
    ];
    element.settings = { ...defaultSettings, default_power_entity_id: "sensor.plug_power" };
    element.testResult = goodPowerMeterDiagnostic;
    const cleared = vi.fn();
    element.addEventListener("test-clear", cleared);
    document.body.append(element);
    await element.updateComplete;

    const powerSensor = element.shadowRoot.querySelector('select[name="default_power_entity_id"]') as HTMLSelectElement;
    powerSensor.value = "sensor.other_power";
    powerSensor.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect(element.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();

    element.testResult = goodPowerMeterDiagnostic;
    await element.updateComplete;
    const meterType = element.shadowRoot.querySelector('select[name="power_meter"]') as HTMLSelectElement;
    meterType.value = "shelly";
    meterType.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect(element.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();

    element.testResult = goodPowerMeterDiagnostic;
    await element.updateComplete;
    const shellyIp = element.shadowRoot.querySelector('input[name="shelly_ip"]') as HTMLInputElement;
    shellyIp.value = "10.0.0.7";
    shellyIp.dispatchEvent(new Event("input"));
    await element.updateComplete;
    expect(element.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();
    expect(cleared).toHaveBeenCalledTimes(3);
  });
});

describe("preflight power meter diagnostics", () => {
  it("explains preparation and provides immediate feedback while the session initializes", async () => {
    const element = document.createElement("measure-preflight-view") as HTMLElement & {
      confirmationAction: string; busy: boolean; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.confirmationAction = "Start averaging";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("you will explicitly start the measurement on the next screen");
    expect(element.shadowRoot.querySelector("button.primary")?.textContent).toBe("Prepare measurement");

    element.busy = true;
    await element.updateComplete;
    const status = element.shadowRoot.querySelector(".starting");
    expect(status?.getAttribute("role")).toBe("status");
    expect(status?.getAttribute("aria-live")).toBe("polite");
    expect(status?.textContent).toContain("Initializing measurement session");
    expect(status?.textContent).toContain("This can take a few seconds");
    expect((element.shadowRoot.querySelector("button.primary") as HTMLButtonElement).disabled).toBe(true);
    expect((element.shadowRoot.querySelector(".actions button") as HTMLButtonElement).disabled).toBe(true);
  });

  it("keeps direct measurements as a single Start measurement action", async () => {
    const element = document.createElement("measure-preflight-view") as HTMLElement & {
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector("button.primary")?.textContent).toBe("Start measurement");
    expect(element.shadowRoot.textContent).not.toContain("explicitly start");
  });

  it("shows the same quality details before a measurement starts", async () => {
    const element = document.createElement("measure-preflight-view") as HTMLElement & {
      powerMeterDiagnostic: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.powerMeterDiagnostic = goodPowerMeterDiagnostic;
    document.body.append(element);
    await element.updateComplete;

    const diagnostic = element.shadowRoot.querySelector("measure-power-meter-diagnostic") as HTMLElement & { updateComplete: Promise<boolean>; shadowRoot: ShadowRoot };
    await diagnostic.updateComplete;
    expect(diagnostic.getAttribute("heading")).toBe("Measurement device quality");
    expect(diagnostic.shadowRoot.textContent).toContain("1.8 s");
    expect(diagnostic.shadowRoot.textContent).toContain("Good");
  });

  it("shows every completed low-load probe point and measured power", async () => {
    const element = document.createElement("measure-preflight-view") as HTMLElement & {
      lightLoadProbe: NonNullable<PreflightResponse["light_load_probe"]>;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.lightLoadProbe = {
      checked_variations: 2,
      minimum_aggregate_power_w: 0.9,
      points: [
        { label: "Color 120° / 100% saturation · brightness 1", mode: "hs", power_w: 0.9 },
        { label: "Color temperature 454 mired · brightness 1", mode: "color_temp", power_w: 1.25 },
      ],
    };
    document.body.append(element);
    await element.updateComplete;

    const results = element.shadowRoot.querySelector('[aria-label="Low-load light check results"]');
    expect(results?.textContent).toContain("Low-load light check passed");
    expect(results?.textContent).toContain("Color 120° / 100% saturation · brightness 1");
    expect(results?.textContent).toContain("0.900 W aggregate");
    expect(results?.textContent).toContain("Color temperature 454 mired · brightness 1");
    expect(results?.textContent).toContain("1.250 W aggregate");
  });
});

describe("app shell", () => {
  it("adds active low-load probe results to the review metrics", () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.request = {
      measure_type: "light",
      model_id: "test",
      product_name: "Test light",
      measure_device: "Test meter",
      generate_model: true,
      parameters: capabilities.defaults,
      power_meter: { type: "hass", entity_id: "sensor.plug_power" },
      controller: { type: "hass", entity_id: "light.test" },
      modes: ["hs"],
      gzip: true,
      multiple_light_count: 1,
      resume_policy: "new",
    };
    element.preflight = {
      valid: true,
      warnings: [],
      light_load_probe: {
        checked_variations: 3,
        minimum_aggregate_power_w: 0.9,
        points: [
          { label: "Color 0° / 100% saturation · brightness 1", mode: "hs", power_w: 1.2 },
          { label: "Color 120° / 100% saturation · brightness 1", mode: "hs", power_w: 0.9 },
          { label: "Color 240° / 100% saturation · brightness 1", mode: "hs", power_w: 1.1 },
        ],
      },
    };

    const metrics = (element as unknown as { reviewMetrics: () => { label: string; value: string }[] }).reviewMetrics();

    expect(metrics).toContainEqual({ label: "Low-load checks", value: "3" });
    expect(metrics).toContainEqual({ label: "Lowest aggregate load", value: "0.900 W" });
  });

  it("shows the auto-discovered battery sensor in the charging preflight review", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.definitions = [{
      measure_type: "charging",
        icon: "🔋",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }, { name: "sample_count", label: "Samples per reading", hint: "More samples reduce noise but increase measurement time.", group: "Sampling" }, { name: "sleep_time_sample", label: "Time between samples (seconds)", hint: "Only used when taking more than one sample.", group: "Sampling", requires_multiple: "sample_count" }],
      label: "Charging device",
      description: "Measure charging power.",
      fields: [],
      supports_profile: true,
      supports_resume: false,
    }];
    element.request = {
      measure_type: "charging",
      model_id: "vacuum",
      product_name: "Vacuum",
      measure_device: "Shelly Plug S",
      generate_model: true,
      parameters: capabilities.defaults,
      power_meter: { type: "hass", entity_id: "sensor.plug_power" },
      controller: { type: "hass", entity_id: "vacuum.robot" },
      charging_device_type: "vacuum_robot",
      resume_policy: "new",
    };
    element.preflight = {
      valid: true,
      warnings: [],
      battery_level_entity_id: "sensor.robot_battery",
      battery_level_attribute: null,
    };
    element.view = "review";
    document.body.append(element);
    await element.updateComplete;

    const review = element.shadowRoot?.querySelector("measure-preflight-view") as HTMLElement & {
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    await review.updateComplete;
    expect(review.shadowRoot.textContent).toContain("Battery");
    expect(review.shadowRoot.textContent).toContain("sensor.robot_battery");
  });

  it("passes a workflow-specific confirmation action through review and ready states", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.definitions = [{
      measure_type: "average",
        icon: "📊",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }],
      label: "Average",
      description: "Measure average power.",
      fields: [],
      supports_profile: false,
      supports_resume: false,
      confirmation_action: "Start averaging",
    }];
    element.request = {
      measure_type: "average",
      model_id: "measurement",
      product_name: "Measurement",
      measure_device: "Shelly Plug S",
      generate_model: false,
      duration: 60,
      parameters: capabilities.defaults,
      power_meter: { type: "hass", entity_id: "sensor.plug_power" },
      resume_policy: "new",
    };
    element.preflight = { valid: true, warnings: [] };
    element.view = "review";
    document.body.append(element);
    await element.updateComplete;

    const review = element.shadowRoot?.querySelector("measure-preflight-view") as HTMLElement & { confirmationAction: string; updateComplete: Promise<boolean> };
    expect(review.confirmationAction).toBe("Start averaging");

    element.snapshot = { state: "awaiting_confirmation", request: element.request };
    element.view = "running";
    await element.updateComplete;
    const running = element.shadowRoot?.querySelector("measure-running-view") as HTMLElement & {
      confirmationAction: string; warningConfirmation: boolean; updateComplete: Promise<boolean>;
    };
    expect(running.confirmationAction).toBe("Start averaging");
    expect(running.warningConfirmation).toBe(false);
  });

  it("marks speaker confirmation as a warning", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.definitions = [{
      measure_type: "speaker",
      icon: "🔊",
      model_id_example: "WSP002",
      product_name_example: "",
      parameters: [],
      label: "Speaker",
      description: "Measure a speaker.",
      fields: [],
      supports_profile: true,
      supports_resume: false,
      confirmation_action: "Start speaker measurement",
      confirmation_is_warning: true,
    }];
    element.request = {
      measure_type: "speaker",
      model_id: "speaker",
      product_name: "Speaker",
      measure_device: "Shelly Plug S",
      generate_model: true,
      parameters: capabilities.defaults,
      power_meter: { type: "hass", entity_id: "sensor.plug_power" },
      controller: { type: "dummy" },
      disable_streaming: false,
      resume_policy: "new",
    };
    element.snapshot = { state: "awaiting_confirmation", request: element.request };
    element.view = "running";
    document.body.append(element);
    await element.updateComplete;

    const running = element.shadowRoot?.querySelector("measure-running-view") as HTMLElement & {
      warningConfirmation: boolean; updateComplete: Promise<boolean>;
    };
    expect(running.warningConfirmation).toBe(true);
  });

  it("loads the Powercalc SVG logo", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    document.body.append(element);
    await element.updateComplete;

    const logo = element.shadowRoot?.querySelector<HTMLImageElement>(".brand-logo");
    expect(logo?.src).toContain("image/svg+xml");
  });

  it("renders calibration lookup failures as a retryable warning", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.view = "setup";
    element.dummyLoadCalibrationError = "Could not load the saved dummy-load calibration: API unavailable";
    document.body.append(element);
    await element.updateComplete;

    const warning = element.shadowRoot?.querySelector(".calibration-warning");
    expect(warning?.getAttribute("role")).toBe("status");
    expect(warning?.textContent).toContain("API unavailable");
    expect(warning?.querySelector("button")?.textContent).toContain("Retry");
  });

  it("does not restore a stale validation result after meter settings change", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.view = "settings";
    element.settings = { ...defaultSettings, default_power_entity_id: "sensor.plug_power", default_measure_device: "Shelly Plug S" };
    element.powers = [
      { entity_id: "sensor.plug_power", name: "Plug power" },
      { entity_id: "sensor.other_power", name: "Other power" },
    ];
    element.powerMeterTestResult = goodPowerMeterDiagnostic;
    document.body.append(element);
    await element.updateComplete;

    const settings = element.shadowRoot?.querySelector("measure-settings-view") as HTMLElement & { updateComplete: Promise<boolean>; shadowRoot: ShadowRoot };
    await settings.updateComplete;
    const powerSensor = settings.shadowRoot.querySelector('select[name="default_power_entity_id"]') as HTMLSelectElement;
    powerSensor.value = "sensor.other_power";
    powerSensor.dispatchEvent(new Event("change"));
    await settings.updateComplete;
    await element.updateComplete;

    expect(element.powerMeterTestResult).toBeUndefined();
    expect(settings.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();
  });

  it("keeps Settings in the app bar and labels each measurement step", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.view = "running";
    element.snapshot = { state: "running" };
    document.body.append(element);
    await element.updateComplete;

    const topbar = element.shadowRoot?.querySelector(".topbar");
    const steps = [...(element.shadowRoot?.querySelectorAll(".sequence > li") ?? [])];
    const running = element.shadowRoot?.querySelector("measure-running-view") as HTMLElement & { diagnosticsUrl: string };
    expect(topbar?.querySelector(".settings-toggle")?.textContent).toContain("Settings");
    expect(steps.map((step) => step.textContent?.trim())).toEqual(["✓Set up", "✓Review", "3Measure", "4Result"]);
    expect(steps.at(2)?.getAttribute("aria-current")).toBe("step");
    expect(new URL(running.diagnosticsUrl).pathname).toContain("/api/session/current/diagnostics");
  });
});

describe("result view", () => {
  it.each(["completed", "failed", "cancelled", "resumable"] as const)("offers diagnostics for a %s session without generated files", async (state) => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      diagnosticsUrl: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state };
    element.diagnosticsUrl = "http://ha.local/ingress/api/session/current/diagnostics";
    document.body.append(element);
    await element.updateComplete;

    const diagnostics = element.shadowRoot.querySelector(".diagnostics-download a") as HTMLAnchorElement;
    expect(diagnostics.textContent).toBe("Download diagnostics");
    expect(diagnostics.href).toBe(element.diagnosticsUrl);
    expect(element.shadowRoot.querySelector(".diagnostics-download")?.textContent).toContain("snapshot and logs");
  });

  it("keeps failed results focused on the actionable error", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      files: { name: string; size: number; media_type: string }[];
      plotCollection: { partial: boolean; plots: never[]; warnings: string[] };
      diagnosticsUrl: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "failed",
      error: "Use a more sensitive meter. See https://docs.powercalc.nl/contributing/measure/troubleshooting/ for troubleshooting guidance.",
    };
    element.files = [{ name: "brightness.csv", size: 10, media_type: "text/csv" }];
    element.plotCollection = { partial: true, plots: [], warnings: ["Could not plot brightness.csv"] };
    element.diagnosticsUrl = "http://ha.local/ingress/api/session/current/diagnostics";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".notice.error")?.textContent).toContain("Use a more sensitive meter.");
    const troubleshootingLink = element.shadowRoot.querySelector(".notice.error a") as HTMLAnchorElement;
    expect(troubleshootingLink.textContent).toBe("Troubleshooting guide");
    expect(troubleshootingLink.href).toBe("https://docs.powercalc.nl/contributing/measure/troubleshooting/");
    expect(element.shadowRoot.textContent).toContain("correct the problem");
    expect(element.shadowRoot.textContent).not.toContain("Could not plot");
    expect(element.shadowRoot.textContent).not.toContain("Generated files");
    expect(element.shadowRoot.textContent).not.toContain("Download all");
    expect(element.shadowRoot.querySelector(".diagnostics-download a")).toBeTruthy();
  });

  it("shows a download-all action for generated files", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      files: { name: string; size: number; media_type: string }[];
      fileUrl: (name: string) => string;
      downloadAll: () => void;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    const downloadAll = vi.fn();
    element.snapshot = { state: "completed" };
    element.files = [
      { name: "model.csv", size: 1234, media_type: "text/csv" },
      { name: "model.json", size: 5678, media_type: "application/json" },
    ];
    element.fileUrl = (name) => `/download/${name}`;
    element.downloadAll = downloadAll;
    document.body.append(element);
    await element.updateComplete;

    const button = element.shadowRoot.querySelector(".download-all") as HTMLButtonElement;
    expect(button.textContent).toContain("Download all");
    button.click();
    expect(downloadAll).toHaveBeenCalledTimes(1);

    const contribution = element.shadowRoot.querySelector(".contribution");
    expect(contribution?.textContent).toContain("Contribute your measurement");
    // Without an eligible GitHub draft, the manual method is selected by default.
    const nextSteps = element.shadowRoot.querySelector(".contribution-next");
    expect(nextSteps?.textContent).toContain("Download and inspect the generated files");
    expect(nextSteps?.textContent).toContain("profile_library/<manufacturer>/<model>/");
    const guide = nextSteps?.querySelector("a") as HTMLAnchorElement;
    expect(guide.href).toBe("https://docs.powercalc.nl/contributing/measure/output/");
    expect(guide.target).toBe("_blank");
    expect(guide.rel).toContain("noopener");
  });

  it("defaults to the GitHub method for an eligible draft and offers manual as an alternative", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      files: { name: string; size: number; media_type: string }[];
      fileUrl: (name: string) => string;
      downloadAll: () => void;
      contributionAuth: { connected: boolean; identity: { login: string } };
      contributionPreview: {
        eligible: boolean;
        repository: string;
        base_branch: string;
        manufacturer_name: string;
        manufacturer_directory: string;
        model_id: string;
        product_name: string;
        contributor: string;
        device_info: Record<string, string>;
        home_assistant: Record<string, string>;
        notes: string;
        files: { path: string; rendered_json: Record<string, string> }[];
        model_json: Record<string, string>;
        commit_message: string;
        pr_title: string;
        pr_body: string;
        branch_name: string;
        warnings: string[];
      };
      contributionResult: { status: string; pull_request_url: string };
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed" };
    element.files = [{ name: "model.json", size: 5678, media_type: "application/json" }];
    element.fileUrl = (name) => `/download/${name}`;
    element.downloadAll = () => {};
    element.contributionAuth = { connected: true, identity: { login: "octocat" } };
    element.contributionPreview = {
      eligible: true,
      repository: "bramstroker/homeassistant-powercalc",
      base_branch: "master",
      manufacturer_name: "Signify",
      manufacturer_directory: "signify",
      model_id: "LCT010",
      product_name: "Hue lamp",
      contributor: "octocat",
      device_info: { device: "light.desk" },
      home_assistant: { version: "2026.7" },
      notes: "Measured through the HA app.",
      files: [{ path: "profile_library/signify/LCT010/model.json", rendered_json: { name: "Hue lamp" } }],
      model_json: { name: "Hue lamp" },
      commit_message: "Add Signify LCT010",
      pr_title: "Add Signify LCT010",
      pr_body: "Adds a measured profile.",
      branch_name: "measure/signify-lct010",
      warnings: [],
    };
    element.contributionResult = { status: "success", pull_request_url: "https://github.com/bramstroker/homeassistant-powercalc/pull/1" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".download-all")).toBeTruthy();
    // GitHub is the default method for an eligible draft; the manual panel is not shown yet.
    const cards = Array.from(element.shadowRoot.querySelectorAll(".method-card")) as HTMLButtonElement[];
    expect(cards.map((card) => card.textContent)).toEqual([
      expect.stringContaining("GitHub pull request"),
      expect.stringContaining("Manual contribution"),
      expect.stringContaining("Add to this installation"),
    ]);
    const [githubCard, manualCard, localCard] = cards as [HTMLButtonElement, HTMLButtonElement, HTMLButtonElement];
    expect(githubCard.getAttribute("aria-checked")).toBe("true");
    expect(localCard.disabled).toBe(true); // local install is not available yet
    expect(element.shadowRoot.querySelector(".contribution-next")).toBeNull();
    const automatic = element.shadowRoot.querySelector(".contribution-auto");
    expect(automatic?.textContent).toContain("Connected to GitHub as octocat");
    expect(automatic?.textContent).toContain("profile_library/signify/LCT010/model.json");
    expect(automatic?.textContent).toContain("Add Signify LCT010");
    expect(automatic?.textContent).not.toContain("aliases");

    const previewed = new Promise<unknown>((resolve) => element.addEventListener("contribution-preview", (event) => resolve((event as CustomEvent).detail)));
    (element.shadowRoot.querySelector('input[name="manufacturer_directory"]') as HTMLInputElement).value = "philips";
    (element.shadowRoot.querySelector(".contribution-form") as HTMLFormElement).requestSubmit();
    expect(await previewed).toMatchObject({ manufacturer_directory: "philips" });

    const submit = element.shadowRoot.querySelector(".contribution-auto button.primary") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    (element.shadowRoot.querySelector('input[name="confirm_contribution"]') as HTMLInputElement).click();
    await element.updateComplete;
    expect((element.shadowRoot.querySelector(".contribution-auto button.primary") as HTMLButtonElement).disabled).toBe(false);
    const submitted = new Promise<unknown>((resolve) => element.addEventListener("contribution-submit", (event) => resolve((event as CustomEvent).detail)));
    (element.shadowRoot.querySelector(".contribution-auto button.primary") as HTMLButtonElement).click();
    expect(await submitted).toMatchObject({ confirmed: true, manufacturer_directory: "philips" });
    expect((element.shadowRoot.querySelector(".success-link") as HTMLAnchorElement).href).toBe(element.contributionResult.pull_request_url);

    // Switching to the manual method reveals the download guide instead of the GitHub form.
    manualCard.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".contribution-auto")).toBeNull();
    expect(element.shadowRoot.querySelector(".contribution-next")?.textContent).toContain("Read the contribution guide");
  });

  it("asks to open settings on the GitHub section when GitHub is not connected", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      contributionAuth: { connected: boolean };
      contributionDraft: { eligible: boolean; manufacturer_name: string; manufacturer_directory: string; model_id: string; product_name: string; contributor: string; notes: string; device_info: Record<string, string>; home_assistant: Record<string, string> };
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed" };
    element.contributionAuth = { connected: false };
    element.contributionDraft = {
      eligible: true, manufacturer_name: "Signify", manufacturer_directory: "signify", model_id: "LCT010",
      product_name: "Hue lamp", contributor: "", notes: "", device_info: {}, home_assistant: {},
    };
    document.body.append(element);
    await element.updateComplete;

    const opened = new Promise<unknown>((resolve) => element.addEventListener("open-settings", (event) => resolve((event as CustomEvent).detail)));
    const button = [...element.shadowRoot.querySelectorAll<HTMLButtonElement>("button")].find((candidate) => candidate.textContent?.includes("Open GitHub settings"));
    button?.click();
    expect(await opened).toEqual({ section: "github" });
  });

  it.each(["failed", "cancelled", "resumable"] as const)("does not suggest contribution for a %s session", async (state) => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".contribution-next")).toBeNull();
  });

  it("renders a summary readout for a file-less measurement", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot; files: { name: string; size: number; media_type: string }[];
      fileUrl: (name: string) => string; downloadAll: () => void;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed", summary: { "Average power": "42.3 W", "Duration": "30 s" } };
    element.files = [];
    element.fileUrl = (name) => name;
    element.downloadAll = () => {};
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".readout")?.textContent).toContain("42.3 W");
    expect(element.shadowRoot.querySelector("#result-title")?.textContent).toContain("Measurement complete");
    expect(element.shadowRoot.textContent).not.toContain("No downloadable files");
    expect(element.shadowRoot.querySelector(".contribution-next")?.textContent).toContain("Use the measured result above in a Powercalc profile");
  });

  it("renders partial plots and offers a PNG download", async () => {
    const context = {
      setTransform: vi.fn(), clearRect: vi.fn(), fillRect: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(),
      lineTo: vi.fn(), stroke: vi.fn(), arc: vi.fn(), fill: vi.fn(), fillText: vi.fn(), save: vi.fn(),
      restore: vi.fn(), translate: vi.fn(), rotate: vi.fn(), measureText: vi.fn(() => ({ width: 10 })),
    } as unknown as CanvasRenderingContext2D;
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,plot");
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      plotCollection: {
        partial: boolean;
        warnings: string[];
        plots: {
          id: string; title: string; kind: "scatter"; x_label: string; y_label: string; source: string;
          series: { label: null; color: string; points: { x: number; y: number; color: null }[] }[];
        }[];
      };
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "cancelled" };
    element.plotCollection = {
      partial: true,
      warnings: [],
      plots: [{
        id: "brightness", title: "Brightness", kind: "scatter", x_label: "Brightness", y_label: "Power (W)",
        source: "LCT010/brightness.csv",
        series: [{ label: null, color: "#5488e8", points: [{ x: 1, y: 0.5, color: null }] }],
      }],
    };
    document.body.append(element);
    await element.updateComplete;

    const plot = element.shadowRoot.querySelector("measure-result-plot") as HTMLElement & {
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    await plot.updateComplete;
    expect(plot.shadowRoot.textContent).toContain("Partial result");
    (plot.shadowRoot.querySelector(".plot-download") as HTMLButtonElement).click();
    expect(click).toHaveBeenCalled();
  });
});
