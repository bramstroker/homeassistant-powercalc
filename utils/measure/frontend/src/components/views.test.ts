import type { AppSettings, Capabilities, EntityDescriptor, MeasureDefinition, MeasurementRunRequest, SessionSnapshot } from "../types";
import { AppShell } from "./app-shell";
import "./result-view";
import "./running-view";
import "./settings-view";
import "./setup-view";

const capabilities: Capabilities = {
  modes: ["brightness", "color_temp", "hs", "effect"],
  defaults: { sleep_time: 1, sample_count: 5, brightness_step: 5, hue_step: 10, saturation_step: 10, color_temp_step: 5 },
};

const lights: EntityDescriptor[] = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"] }];

describe("setup view", () => {
  it("renders dynamic entities, mode choices, and collapsed advanced settings", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      selectedType: string;
      selectedLightId: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.selectedType = "Light bulb(s)";
    element.selectedLightId = "light.desk";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Desk lamp · light.desk");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.querySelector("details")?.open).toBe(false);
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);

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
    element.selectedType = "Light bulb(s)";
    document.body.append(element);
    await element.updateComplete;

    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toEqual(["brightness", "color_temp", "hs", "effect"]);
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
    element.selectedType = "Light bulb(s)";
    document.body.append(element);
    await element.updateComplete;

    const labels = [...element.shadowRoot.querySelectorAll("label.check")].map((label) => label.textContent?.trim());
    expect(labels).toContain("Effect");
    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toContain("effect");
  });
});

const definitions: MeasureDefinition[] = [
  { measure_type: "Light bulb(s)", label: "Light bulb(s)", description: "Build a lookup-table power profile for a light.", fields: [], supports_profile: true, supports_resume: true },
  {
    measure_type: "Average",
    label: "Average",
    description: "Measure average power for a fixed duration.",
    fields: [
      { name: "powermeter_entity_id", label: "Power sensor", control: "entity", required: true, options: [] },
      { name: "duration", label: "Duration (seconds)", control: "number", required: true, options: [], default: 60 },
    ],
    supports_profile: false,
    supports_resume: false,
  },
];

describe("setup type picker", () => {
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

  it("renders generic fields, dedupes the power sensor, and emits preflight-run for a non-light type", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; powers: EntityDescriptor[]; powerMeter: string;
      defaultPowerEntityId: string; selectedType: string; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.definitions = definitions;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.powerMeter = "hass";
    element.defaultPowerEntityId = "sensor.plug_power";
    element.selectedType = "Average";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="power_entity_id"]')).toBeTruthy();
    expect(element.shadowRoot.querySelector('input[name="duration"]')).toBeTruthy();
    // The powermeter field from the definition must not be rendered a second time.
    expect(element.shadowRoot.querySelectorAll('[name="powermeter_entity_id"]')).toHaveLength(0);

    const submitted = new Promise<MeasurementRunRequest>((resolve) => {
      element.addEventListener("preflight-run", (event) => resolve((event as CustomEvent<MeasurementRunRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();
    const request = await submitted;
    expect(request.measure_type).toBe("Average");
    expect(request.answers.powermeter_entity_id).toBe("sensor.plug_power");
    expect(request.answers.duration).toBe(60);
  });

  it("renders an entity dropdown for a device domain when entities are available", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "Fan",
      label: "Fan",
      description: "Measure fan power across percentage levels.",
      fields: [
        { name: "powermeter_entity_id", label: "Power sensor", control: "entity", required: true, options: [] },
        { name: "entity_id", label: "Fan", control: "entity", required: true, entity_domain: "fan", options: [] },
      ],
      supports_profile: true,
      supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      definitions: MeasureDefinition[]; powers: EntityDescriptor[]; powerMeter: string;
      deviceEntities: Record<string, EntityDescriptor[]>; selectedType: string;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.definitions = [fanDefinition];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.powerMeter = "hass";
    element.deviceEntities = { fan: [{ entity_id: "fan.bedroom", name: "Bedroom fan" }] };
    element.selectedType = "Fan";
    document.body.append(element);
    await element.updateComplete;

    const fanSelect = element.shadowRoot.querySelector('select[name="entity_id"]') as HTMLSelectElement;
    expect(fanSelect).toBeTruthy();
    expect(fanSelect.textContent).toContain("Bedroom fan · fan.bedroom");
  });
});

describe("running view", () => {
  it("shows progress, phase, connection state, and cancellation", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      connected: boolean;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", phase: "Brightness", mode: "brightness", progress: { completed: 25, total: 100, estimated_remaining_seconds: 120 } };
    element.connected = true;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("25%");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.textContent).toContain("Live");
    expect(element.shadowRoot.querySelector("progress")?.value).toBe(25);
    expect(element.shadowRoot.querySelector("button")?.textContent).toContain("Cancel measurement");
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
  it("preselects the default power sensor for a new measurement", async () => {
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
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.defaultPowerEntityId = "sensor.plug_power";
    element.selectedType = "Light bulb(s)";
    document.body.append(element);
    await element.updateComplete;

    const power = element.shadowRoot.querySelector('select[name="power_entity_id"]') as HTMLSelectElement;
    expect(power.value).toBe("sensor.plug_power");
  });

  it("keeps the voltage selector aligned to the form grid and pairs it with the power sensor", async () => {
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
      { entity_id: "sensor.plug_power", name: "Plug power", unit: "W" },
      { entity_id: "sensor.strip_power", name: "Strip power", unit: "W" },
    ];
    element.voltages = [
      { entity_id: "sensor.plug_voltage", name: "Plug voltage", unit: "V" },
      { entity_id: "sensor.strip_voltage", name: "Strip voltage", unit: "V" },
    ];
    element.defaultPowerEntityId = "sensor.plug_power";
    element.selectedType = "Light bulb(s)";
    document.body.append(element);
    await element.updateComplete;

    const voltage = element.shadowRoot.querySelector('select[name="voltage_entity_id"]') as HTMLSelectElement;
    expect(voltage.value).toBe("sensor.plug_voltage");
    expect(voltage.closest(".grid")?.children).toHaveLength(1);

    const power = element.shadowRoot.querySelector('select[name="power_entity_id"]') as HTMLSelectElement;
    power.value = "sensor.strip_power";
    power.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect(voltage.value).toBe("sensor.strip_voltage");
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
    element.settings = { default_power_entity_id: null, default_measure_device: null, power_meter: "hass", shelly_ip: null };
    document.body.append(element);
    await element.updateComplete;

    const saved = new Promise<AppSettings>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    const select = element.shadowRoot.querySelector('select[name="default_power_entity_id"]') as HTMLSelectElement;
    select.value = "sensor.plug_power";
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await saved).default_power_entity_id).toBe("sensor.plug_power");
  });
});

describe("app shell device entities", () => {
  it("fetches device entities per domain during boot and exposes them for the picker", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "Fan", label: "Fan", description: "Measure fan power across percentage levels.",
      fields: [
        { name: "powermeter_entity_id", label: "Power sensor", control: "entity", required: true, options: [], entity_domain: "sensor" },
        { name: "entity_id", label: "Fan", control: "entity", required: true, entity_domain: "fan", options: [] },
      ],
      supports_profile: true, supports_resume: false,
    };
    const requestedDomains: string[] = [];
    const element = new AppShell();
    (element as unknown as { api: unknown }).api = {
      getCapabilities: async () => capabilities,
      getEntities: async () => [],
      getSettings: async () => ({ default_power_entity_id: null, default_measure_device: null, power_meter: "hass", shelly_ip: null }),
      getCurrent: async () => ({ state: "idle" }),
      getMeasureDefinitions: async () => [fanDefinition],
      getEntitiesByDomain: async (domain: string) => {
        requestedDomains.push(domain);
        return domain === "fan" ? [{ entity_id: "fan.bedroom", name: "Bedroom fan" }] : [];
      },
    };

    await (element as unknown as { boot: () => Promise<void> }).boot();

    expect(requestedDomains).toEqual(["fan"]);
    expect(element.deviceEntities.fan).toEqual([{ entity_id: "fan.bedroom", name: "Bedroom fan" }]);
  });
});

describe("settings power meter test", () => {
  it("emits a test event with the current form values and shows the result", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testResult: { success: boolean; power?: number | null; message?: string | null };
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = { default_power_entity_id: null, default_measure_device: null, power_meter: "shelly", shelly_ip: "192.168.1.50" };
    document.body.append(element);
    await element.updateComplete;

    const tested = new Promise<AppSettings>((resolve) => {
      element.addEventListener("test", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    const testButton = [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Test connection"));
    testButton?.click();
    const detail = await tested;
    expect(detail.power_meter).toBe("shelly");
    expect(detail.shelly_ip).toBe("192.168.1.50");

    element.testResult = { success: true, power: 12.3 };
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".test-result.ok")?.textContent).toContain("12.3 W");
  });

  it("keeps the selected meter and Shelly IP across a re-render", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testing: boolean;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = { default_power_entity_id: null, default_measure_device: null, power_meter: "hass", shelly_ip: null };
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
});

describe("app shell", () => {
  it("keeps Settings in the app bar and labels each measurement step", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.view = "running";
    element.snapshot = { state: "running" };
    document.body.append(element);
    await element.updateComplete;

    const topbar = element.shadowRoot?.querySelector(".topbar");
    const steps = [...(element.shadowRoot?.querySelectorAll(".sequence > li") ?? [])];
    expect(topbar?.querySelector(".settings-toggle")?.textContent).toContain("Settings");
    expect(steps.map((step) => step.textContent?.trim())).toEqual(["✓Set up", "✓Review", "3Measure", "4Result"]);
    expect(steps.at(2)?.getAttribute("aria-current")).toBe("step");
  });
});

describe("result view", () => {
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
  });
});
