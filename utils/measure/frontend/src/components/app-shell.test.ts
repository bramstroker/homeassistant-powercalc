import type { MeasureDefinition, MeasureParameter, MeasurementRequest } from "../types";
import { AppShell } from "./app-shell";
import { capabilities, controllerOf, defaultSettings, goodPowerMeterDiagnostic } from "./test-fixtures";

describe("app shell device entities", () => {
  it("loads device entities only after their measurement type is selected", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan",
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }] satisfies MeasureParameter[], label: "Fan", description: "Measure fan power across percentage levels.",
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
      getSessions: async () => [],
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
    controllerOf(element).selectMeasureType("fan");
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
      getSessions: async () => [],
      getSession: async () => ({
        state: "completed",
        session_id: "session-1",
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
    void controllerOf(element).duplicateSession("session-1");

    await vi.waitFor(() => expect(element.request?.measure_type).toBe("average"));
    expect(element.view).toBe("setup");
  });
});

describe("app shell", () => {
  it("shows the auto-discovered battery sensor in the charging preflight review", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.definitions = [{
      measure_type: "charging",
        icon: "🔋",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }, { name: "sample_count", label: "Samples per reading", hint: "More samples reduce noise but increase measurement time.", group: "Sampling" }, { name: "sleep_time_sample", label: "Time between samples (seconds)", hint: "Only used when taking more than one sample.", group: "Sampling", requires_multiple: "sample_count" }] satisfies MeasureParameter[],
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
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }] satisfies MeasureParameter[],
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
    // The shell holds its state as plain fields; the controller asks for the re-render.
    element.requestUpdate();
    await element.updateComplete;
    const running = element.shadowRoot?.querySelector("measure-running-view") as HTMLElement & {
      confirmationAction: string; warningConfirmation: boolean; updateComplete: Promise<boolean>;
    };
    expect(running.confirmationAction).toBe("Start averaging");
    expect(running.warningConfirmation).toBe(false);
  });

  it("uses checkpoint actions for the two-step dummy-load workflow", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.request = {
      measure_type: "average",
      model_id: "measurement",
      product_name: "Measurement",
      measure_device: "Shelly Plug S",
      generate_model: false,
      duration: 60,
      parameters: capabilities.defaults,
      power_meter: { type: "hass", entity_id: "sensor.plug_power" },
      dummy_load: { mode: "calibrate", description: "60 W lamp" },
      resume_policy: "new",
    };
    element.preflight = { valid: true, warnings: [] };
    element.view = "review";
    document.body.append(element);
    await element.updateComplete;

    const review = element.shadowRoot?.querySelector("measure-preflight-view") as HTMLElement & { confirmationAction: string };
    expect(review.confirmationAction).toBe("Start measurement");

    element.snapshot = {
      state: "awaiting_confirmation",
      request: element.request,
      confirmation_message: "Disconnect the light and connect only the dummy load.",
      confirmation_action: "Start dummy-load calibration",
    };
    element.view = "running";
    element.requestUpdate();
    await element.updateComplete;

    const running = element.shadowRoot?.querySelector("measure-running-view") as HTMLElement & { confirmationAction: string };
    expect(running.confirmationAction).toBe("Start dummy-load calibration");
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

    expect(element.shadowRoot?.querySelector(".sequence")).toBeNull();
    const settings = element.shadowRoot?.querySelector("measure-settings-view") as HTMLElement & { updateComplete: Promise<boolean>; shadowRoot: ShadowRoot };
    await settings.updateComplete;
    const powerSensor = settings.shadowRoot.querySelector('measure-combobox[name="default_power_entity_id"]') as HTMLElement;
    powerSensor.dispatchEvent(new CustomEvent("combobox-change", {
      detail: { value: "sensor.other_power" }, bubbles: true, composed: true,
    }));
    await settings.updateComplete;
    await element.updateComplete;

    expect(element.powerMeterTestResult).toBeUndefined();
    expect(settings.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();
  });

  it("hides the measurement progress bar outside the measurement flow", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    document.body.append(element);
    await element.updateComplete;

    // The app boots into "loading" and lands on the session overview, so the bar must not flash.
    expect(element.view).toBe("loading");
    expect(element.shadowRoot?.querySelector(".sequence")).toBeNull();

    element.view = "sessions";
    element.requestUpdate();
    await element.updateComplete;
    expect(element.shadowRoot?.querySelector(".sequence")).toBeNull();

    element.view = "setup";
    element.requestUpdate();
    await element.updateComplete;
    expect(element.shadowRoot?.querySelector(".sequence")).not.toBeNull();
  });

  it("keeps Settings in the app bar and labels each measurement step", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.view = "running";
    element.snapshot = { state: "running", session_id: "session-1" };
    document.body.append(element);
    await element.updateComplete;

    const topbar = element.shadowRoot?.querySelector(".topbar");
    const steps = [...(element.shadowRoot?.querySelectorAll(".sequence > li") ?? [])];
    const running = element.shadowRoot?.querySelector("measure-running-view") as HTMLElement & { diagnosticsUrl: string };
    expect(topbar?.querySelector(".brand")?.getAttribute("aria-label")).toBe("Open all measurement sessions");
    expect(topbar?.querySelector(".sessions-toggle")?.textContent).toContain("All sessions");
    expect(topbar?.querySelector(".settings-toggle")?.textContent).toContain("Settings");
    expect(steps.map((step) => step.textContent?.trim())).toEqual(["✓Set up", "✓Review", "3Measure", "4Result", "5Prepare", "6Use profile"]);
    expect(steps.at(2)?.getAttribute("aria-current")).toBe("step");
    expect(new URL(running.diagnosticsUrl).pathname).toContain("/api/sessions/session-1/diagnostics");
  });

  it("scrolls to the top whenever the active screen changes", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.view = "result";
    element.snapshot = { state: "completed", session_id: "session-1" };
    document.body.append(element);
    await element.updateComplete;

    document.documentElement.scrollTop = 500;
    document.documentElement.scrollLeft = 20;
    document.body.scrollTop = 500;
    document.body.scrollLeft = 20;
    element.view = "profile";
    element.requestUpdate();
    await element.updateComplete;
    expect(document.documentElement.scrollTop).toBe(0);
    expect(document.documentElement.scrollLeft).toBe(0);
    expect(document.body.scrollTop).toBe(0);
    expect(document.body.scrollLeft).toBe(0);

    document.documentElement.scrollTop = 500;
    document.body.scrollTop = 500;
    element.requestUpdate();
    await element.updateComplete;
    expect(document.documentElement.scrollTop).toBe(500);
    expect(document.body.scrollTop).toBe(500);
  });

  it.each(["setup", "review", "running", "result"] as const)("ends the average flow at Result in %s", async (view) => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    const request: MeasurementRequest = {
      measure_type: "average", duration: 60, model_id: "", product_name: "", measure_device: "Test meter",
      generate_model: false, parameters: capabilities.defaults, resume_policy: "new", power_meter: { type: "dummy" },
    };
    element.view = view;
    element.selectedMeasureType = view === "setup" ? "average" : "light";
    if (view === "review") element.request = request;
    if (view === "running" || view === "result") {
      element.snapshot = { state: view === "result" ? "completed" : "running", request };
    }
    document.body.append(element);
    await element.updateComplete;
    const steps = [...(element.shadowRoot?.querySelectorAll(".sequence > li") ?? [])];
    expect(steps).toHaveLength(4);
    expect(steps.at(-1)?.textContent).toContain("Result");
    if (view === "result") {
      const result = element.shadowRoot?.querySelector("measure-result-view") as HTMLElement & { updateComplete: Promise<boolean> };
      await result.updateComplete;
      expect(result.shadowRoot?.querySelector(".contribution")).toBeNull();
      expect(steps.at(-1)?.getAttribute("aria-current")).toBe("step");
    }
  });
});
