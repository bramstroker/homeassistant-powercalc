import type { AppSettings, Capabilities, EntityDescriptor, MeasureDefinition, MeasurementRequest, OperatingPoint, PowerMeterDiagnostic, SessionSnapshot } from "../types";
import { sharedStyles } from "../styles";
import { AppShell } from "./app-shell";
import "./result-view";
import "./running-view";
import "./settings-view";
import "./setup-view";

const measurementDefaults = { sleep_time: 1, sample_count: 5, sleep_time_sample: 1, max_retries: 5, max_nudges: 0 };
const defaultSettings: AppSettings = {
  default_power_entity_id: null, default_measure_device: null, power_meter: "hass", shelly_ip: null,
  measurement_defaults: measurementDefaults,
};
const capabilities: Capabilities = {
  modes: ["brightness", "color_temp", "hs", "effect"],
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

const lights: EntityDescriptor[] = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"] }];

it("uses dark native form controls so iOS select indicators remain visible", () => {
  expect(sharedStyles.cssText).toContain("color-scheme: dark");
});

describe("setup view", () => {
  it("renders dynamic entities, mode choices, and collapsed advanced settings", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      selectedType: string;
      selectedLightId: string;
      defaultMeasureDevice: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.selectedType = "light";
    element.selectedLightId = "light.desk";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Desk lamp · light.desk");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.querySelector("details")?.open).toBe(false);
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
    expect(element.shadowRoot.querySelector<HTMLElement>(".effect-settings")?.hidden).toBe(true);
    expect((element.shadowRoot.querySelector('input[name="sleep_time"]') as HTMLInputElement).value).toBe("1");
    expect((element.shadowRoot.querySelector('input[name="sleep_time_sample"]') as HTMLInputElement).disabled).toBe(false);
    expect((element.shadowRoot.querySelector('input[name="bri_bri_steps"]') as HTMLInputElement).value).toBe("1");
    expect((element.shadowRoot.querySelector('input[name="ct_bri_steps"]') as HTMLInputElement).value).toBe("5");
    expect((element.shadowRoot.querySelector('input[name="ct_mired_steps"]') as HTMLInputElement).value).toBe("10");
    expect((element.shadowRoot.querySelector('input[name="hs_bri_steps"]') as HTMLInputElement).value).toBe("32");
    expect((element.shadowRoot.querySelector('input[name="hs_hue_steps"]') as HTMLInputElement).value).toBe("2731");
    expect((element.shadowRoot.querySelector('input[name="hs_sat_steps"]') as HTMLInputElement).value).toBe("32");

    const light = element.shadowRoot.querySelector('select[name="light_entity_id"]') as HTMLSelectElement;
    light.value = "light.desk";
    light.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
  });

  it("auto-selects every supported color mode for a capable light", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      selectedType: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.rgb", name: "RGB lamp", supported_modes: ["brightness", "color_temp", "hs"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toEqual(["brightness", "color_temp", "hs", "effect"]);
  });

  it("submits mode-specific native light-grid steps", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      selectedType: string;
      selectedLightId: string;
      defaultPowerEntityId: string;
      defaultMeasureDevice: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.rgb", name: "RGB lamp", supported_modes: ["brightness", "color_temp", "hs"] }];
    element.powers = [{
      entity_id: "sensor.plug_power",
      name: "Plug power",
      unit: "W",
      related_voltage_entity_id: "sensor.plug_voltage",
    }];
    element.voltages = [{ entity_id: "sensor.plug_voltage", name: "Plug voltage", unit: "V" }];
    element.selectedType = "light";
    element.selectedLightId = "light.rgb";
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

  it("hides the virtual-device toggle unless developer mode is enabled", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      selectedType: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('input[name="use_dummy_controller"]')).toBeNull();
  });

  it("submits a dummy light controller when the developer virtual-device toggle is on", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      selectedType: string;
      defaultMeasureDevice: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = { ...capabilities, developer_mode: true };
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
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
      measure_type: "fan", label: "Fan", description: "Measure fan power.",
      fields: [{ name: "fan_entity_id", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      supports_profile: true, supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; capabilities: Capabilities; powerMeter: string;
      deviceEntities: Record<string, EntityDescriptor[]>;
      selectedType: string;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      selectedType: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.effect", name: "Effect lamp", supported_modes: ["brightness", "effect"], effect_list: ["colorloop"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const labels = [...element.shadowRoot.querySelectorAll("label.check")].map((label) => label.textContent?.trim());
    expect(labels).toContain("Effect");
    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toContain("effect");
    const effectSettings = element.shadowRoot.querySelector<HTMLElement>(".effect-settings");
    expect(effectSettings?.hidden).toBe(false);

    const effect = element.shadowRoot.querySelector<HTMLInputElement>('input[name="modes"][value="effect"]');
    if (!effect) throw new Error("Expected effect mode input");
    effect.checked = false;
    effect.dispatchEvent(new Event("change"));
    expect(effectSettings?.hidden).toBe(true);
    expect((effectSettings?.querySelector("input") as HTMLInputElement).disabled).toBe(true);
  });
});

const definitions: MeasureDefinition[] = [
  { measure_type: "light", label: "Light bulb(s)", description: "Build a lookup-table power profile for a light.", fields: [], supports_profile: true, supports_resume: true },
  {
    measure_type: "average",
    label: "Average",
    description: "Measure average power for a fixed duration.",
    fields: [
      { name: "power_entity_id", label: "Power sensor", control: "entity", required: true, options: [] },
      { name: "duration", label: "Duration (seconds)", control: "number", required: true, options: [], default: 60 },
    ],
    supports_profile: false,
    supports_resume: false,
  },
];

describe("setup type picker", () => {
  it("uses a matching saved dummy-load calibration by default", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; capabilities: Capabilities; powers: EntityDescriptor[]; powerMeter: string;
      defaultPowerEntityId: string; defaultMeasureDevice: string; selectedType: string;
      dummyLoadCalibration: { description: string; resistance: number; calibrated_at: string };
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; capabilities: Capabilities; powerMeter: string;
      selectedType: string; dummyLoadCalibration: null;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; capabilities: Capabilities; powerMeter: string;
      selectedType: string; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[];
      capabilities: Capabilities;
      powers: EntityDescriptor[];
      powerMeter: string;
      defaultPowerEntityId: string;
      selectedType: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; powerMeterConfigured: boolean; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.definitions = definitions;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelectorAll(".type-card")).toHaveLength(2);
    expect(element.shadowRoot.textContent).toContain("Measure average power for a fixed duration.");
    expect(element.shadowRoot.querySelector("form")).toBeNull();
  });

  it("renders generic fields, dedupes the power sensor, and emits one typed preflight request", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; capabilities: Capabilities; powers: EntityDescriptor[]; powerMeter: string;
      defaultPowerEntityId: string; defaultMeasureDevice: string; selectedType: string; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; capabilities: Capabilities; powerMeter: string; shellyIp: string;
      selectedType: string; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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

    expect((await submitted).power_meter).toEqual({ type: "shelly", device_ip: "192.0.2.20" });
  });

  it("renders an entity dropdown for a device domain when entities are available", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan",
      label: "Fan",
      description: "Measure fan power across percentage levels.",
      fields: [
        { name: "power_entity_id", label: "Power sensor", control: "entity", required: true, options: [] },
        { name: "fan_entity_id", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] },
      ],
      supports_profile: true,
      supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; capabilities: Capabilities; powers: EntityDescriptor[]; powerMeter: string;
      deviceEntities: Record<string, EntityDescriptor[]>; selectedType: string;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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
        label: "Fan",
        description: "Measure fan power across percentage levels.",
        fields: [
          { name: "fan_entity_id", label: "Fan", control: "entity" as const, required: true, entity_domains: ["fan"], options: [] },
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
        label: "Speaker",
        description: "Measure power across media-player volume levels.",
        fields: [
          { name: "media_player_entity_id", label: "Media player", control: "entity" as const, required: true, entity_domains: ["media_player"], options: [] },
          { name: "disable_streaming", label: "Disable automatic pink-noise streaming", control: "boolean" as const, required: false, default: false, options: [] },
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
        label: "Charging device",
        description: "Measure charging power against battery level.",
        fields: [
          {
            name: "charging_device_type",
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[];
      capabilities: Capabilities;
      powerMeter: string;
      deviceEntities: Record<string, EntityDescriptor[]>;
      selectedType: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
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
      measure_type: "fan", label: "Fan", description: "Measure fan power.",
      fields: [{ name: "fan_entity_id", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      supports_profile: false, supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; capabilities: Capabilities; powerMeter: string;
      deviceEntityErrors: Record<string, string>; selectedType: string;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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
      measure_type: "charging", label: "Charging device", description: "Measure charging power.",
      fields: [
        {
          name: "charging_device_type", label: "Device type", control: "select", required: true,
          options: [
            { value: "vacuum_robot", label: "Vacuum", entity_domain: "vacuum" },
            { value: "lawn_mower_robot", label: "Lawn mower", entity_domain: "lawn_mower" },
          ],
        },
        {
          name: "charging_entity_id", label: "Charging device", control: "entity", required: true,
          entity_domains: ["vacuum", "lawn_mower"], options: [],
        },
      ],
      supports_profile: false, supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; capabilities: Capabilities; powerMeter: string;
      deviceEntities: Record<string, EntityDescriptor[]>; selectedType: string; errorMessage: string;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
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
    expect(toggle.textContent).toContain("2");

    toggle.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".log-overlay")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".log-overlay")?.textContent).toContain("Second log");
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      defaultPowerEntityId: string;
      defaultMeasureDevice: string;
      selectedType: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.defaultPowerEntityId = "sensor.plug_power";
    element.defaultMeasureDevice = "Shelly Plug S";
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      defaultPowerEntityId: string;
      selectedType: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
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
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const summary = element.shadowRoot.querySelector(".power-meter-summary");
    expect(summary?.textContent).toContain("Plug power · sensor.plug_power");
    expect(summary?.textContent).toContain("Voltage: Plug voltage · sensor.plug_line_voltage");
    expect(element.shadowRoot.querySelector('select[name="voltage_entity_id"]')).toBeNull();
  });

  it("prefills the model ID from the selected measurement device", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      defaultPowerEntityId: string;
      selectedType: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"], device_id: "light-device", model_id: "LWA017" }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", device_id: "plug-device", model_id: "WSP002" }];
    element.voltages = [];
    element.defaultPowerEntityId = "sensor.plug_power";
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
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      selectedType: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power" }];
    element.voltages = [];
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
    expect(labels).toEqual(["Light", "Number of lights", "Model ID", "Full product name"]);
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
    expect(sectionButtons.map((button) => button.textContent?.trim())).toEqual(["Power meter", "Measure tuning"]);
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
});

describe("app shell device entities", () => {
  it("loads device entities only after their measurement type is selected", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan", label: "Fan", description: "Measure fan power across percentage levels.",
      fields: [
        { name: "power_entity_id", label: "Power sensor", control: "entity", required: true, options: [], entity_domains: ["sensor"] },
        { name: "fan_entity_id", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] },
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
      getDummyLoadCalibration: async () => null,
      getCurrent: async () => ({ state: "idle" }),
      getMeasureDefinitions: async () => [fanDefinition],
      getEntitiesByDomain: async (domain: string) => {
        requestedDomains.push(domain);
        return domain === "fan" ? [{ entity_id: "fan.bedroom", name: "Bedroom fan" }] : [];
      },
    };

    await (element as unknown as { boot: () => Promise<void> }).boot();

    expect(requestedDomains).toEqual([]);
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
      { id: "auth", name: "Locked plug", model: null, generation: 2, ip_address: "10.0.0.9", supported: false, reason: "Authentication is not supported yet.", auth_required: true },
    ];
    await element.updateComplete;

    const discovered = element.shadowRoot.querySelector('select[name="discovered_shelly"]') as HTMLSelectElement;
    expect(discovered.options[1]?.textContent).toContain("Kitchen plug");
    expect(discovered.options[2]?.textContent).toContain("Authentication is not supported yet.");
    expect(discovered.options[2]?.disabled).toBe(true);
    discovered.value = "10.0.0.8";
    discovered.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect((element.shadowRoot.querySelector('input[name="shelly_ip"]') as HTMLInputElement).value).toBe("10.0.0.8");
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
});

describe("app shell", () => {
  it("shows the auto-discovered battery sensor in the charging preflight review", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.definitions = [{
      measure_type: "charging",
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
      label: "Speaker",
      description: "Measure a speaker.",
      fields: [],
      supports_profile: true,
      supports_resume: false,
      confirmation_action: "Start speaker measurement",
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

    const nextSteps = element.shadowRoot.querySelector(".contribution-next");
    expect(nextSteps?.textContent).toContain("Contribute your measurement");
    expect(nextSteps?.textContent).toContain("Download and inspect the generated files");
    expect(nextSteps?.textContent).toContain("profile_library/<manufacturer>/<model>/");
    const guide = nextSteps?.querySelector("a") as HTMLAnchorElement;
    expect(guide.href).toBe("https://docs.powercalc.nl/contributing/measure/output/");
    expect(guide.target).toBe("_blank");
    expect(guide.rel).toContain("noopener");
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
