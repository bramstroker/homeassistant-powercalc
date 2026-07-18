import { MeasureAppController } from "./app-controller";
import type { EventConnection, MeasureAppApi, MeasureAppState } from "./app-controller";
import type { PowerMeterDiagnostic, SessionEvent } from "./types";

const measurementDefaults = { sleep_time: 1, sample_count: 2, sleep_time_sample: 1, max_retries: 5, max_nudges: 0 };
const settings = {
  default_power_entity_id: null, default_measure_device: null, power_meter: "hass" as const, shelly_ip: null,
  measurement_defaults: measurementDefaults,
};
const capabilities = {
  modes: ["brightness" as const],
  defaults: {
    ...measurementDefaults,
    bri_bri_steps: 1, ct_bri_steps: 5, ct_mired_steps: 10,
    hs_bri_steps: 32, hs_hue_steps: 2731, hs_sat_steps: 32,
    min_brightness: 1, sleep_initial: 10, sleep_standby: 20,
    effect_bri_steps: 40, measure_time_effect: 180, measure_time_effect_min: 20,
  },
};

function state(): MeasureAppState {
  return {
    view: "loading", errorMessage: "", busy: false, connectedToEvents: false,
    files: [], plotCollection: { partial: false, plots: [], warnings: [] },
    logs: [], samples: [], lights: [], powers: [], voltages: [], definitions: [],
    dummyLoadCalibration: null, dummyLoadCalibrationError: "",
    deviceEntities: {}, deviceEntityErrors: {}, testingPowerMeter: false,
    shellyDiscoveryDevices: [], discoveringShellys: false, shellyDiscoveryError: "",
  };
}

function api(overrides: Partial<MeasureAppApi> = {}): MeasureAppApi {
  return {
    getCapabilities: async () => capabilities,
    getMeasureDefinitions: async () => [],
    getSettings: async () => settings,
    saveSettings: async (value) => value,
    testPowerMeter: async () => ({
      success: true,
      power: 1,
      status: "good",
      precision_decimals: 1,
      max_report_interval_seconds: 2,
      reports_observed: 3,
      duration_seconds: 4,
      precision_status: "good",
      update_interval_status: "good",
      messages: [],
    }),
    getShellyDevices: async () => ({ available: true, message: null, devices: [] }),
    getEntityCatalog: async () => ({ lights: [], powers: [], voltages: [] }),
    getEntitiesByDomain: async () => [],
    getEntitiesByDeviceClass: async () => [],
    getDummyLoadCalibration: async () => null,
    preflight: async () => ({ valid: true, warnings: [] }),
    start: async () => ({ state: "running" }),
    getCurrent: async () => ({ state: "idle" }),
    cancel: async () => ({ state: "cancelled" }),
    confirm: async () => ({ state: "running" }),
    resume: async () => ({ state: "running" }),
    getFiles: async () => [],
    getPlots: async () => ({ partial: false, plots: [], warnings: [] }),
    ...overrides,
  };
}

describe("measure app controller", () => {
  it("loads the matching dummy-load calibration during boot", async () => {
    const appState = state();
    const calibration = {
      description: "60 W incandescent bulb",
      resistance: 882.4,
      calibrated_at: "2026-07-16T10:00:00Z",
      power_meter_fingerprint: "hass:sensor.plug_power:sensor.plug_voltage",
    };
    const controller = new MeasureAppController(appState, () => api({
      getDummyLoadCalibration: async () => calibration,
    }), () => connection(), () => undefined);

    await controller.boot();

    expect(appState.dummyLoadCalibration).toEqual(calibration);
  });

  it("surfaces calibration lookup failures without blocking boot", async () => {
    const appState = state();
    const controller = new MeasureAppController(appState, () => api({
      getDummyLoadCalibration: async () => { throw new Error("Calibration API unavailable"); },
    }), () => connection(), () => undefined);

    await controller.boot();

    expect(appState.view).toBe("setup");
    expect(appState.dummyLoadCalibration).toBeNull();
    expect(appState.dummyLoadCalibrationError).toContain("Calibration API unavailable");
  });

  it("loads files and plots for a persisted terminal session", async () => {
    const appState = state();
    let calibrationCalls = 0;
    const plots = {
      partial: true,
      warnings: ["Partial data"],
      plots: [{
        id: "brightness",
        title: "Brightness",
        kind: "scatter" as const,
        x_label: "Brightness",
        y_label: "Power (W)",
        source: "LCT010/brightness.csv",
        series: [{ label: null, color: "#5488e8", points: [{ x: 1, y: 0.5, color: null }] }],
      }],
    };
    const controller = new MeasureAppController(appState, () => api({
      getCurrent: async () => ({ state: "cancelled" }),
      getFiles: async () => [{ name: "brightness.csv", size: 10, media_type: "text/csv" }],
      getPlots: async () => plots,
      getDummyLoadCalibration: async () => {
        calibrationCalls += 1;
        return calibrationCalls === 1
          ? null
          : { description: "Calibrated load", resistance: 880, calibrated_at: "2026-07-16T10:00:00Z" };
      },
    }), () => connection(), () => undefined);

    await controller.boot();

    expect(appState.view).toBe("result");
    expect(appState.files).toHaveLength(1);
    expect(appState.plotCollection).toEqual(plots);
    expect(appState.dummyLoadCalibration?.description).toBe("Calibrated load");
  });

  it("boots core data and lazily fetches entities for the selected measurement", async () => {
    const requestedDomains: string[] = [];
    let catalogCalls = 0;
    let deviceClassCalls = 0;
    const appState = state();
    const appApi = api({
      getEntityCatalog: async () => {
        catalogCalls += 1;
        return {
          lights: [{ entity_id: "light.desk", name: "Desk" }],
          powers: [{ entity_id: "sensor.plug_power", name: "Plug power" }],
          voltages: [{ entity_id: "sensor.plug_voltage", name: "Plug voltage" }],
        };
      },
      getMeasureDefinitions: async () => [{
        measure_type: "fan", label: "Fan", description: "Measure fan power.", supports_profile: true, supports_resume: false,
        fields: [{ name: "fan_entity_id", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      }],
      getEntitiesByDomain: async (domain) => {
        requestedDomains.push(domain);
        return [{ entity_id: "fan.bedroom", name: "Bedroom fan" }];
      },
      getEntitiesByDeviceClass: async () => {
        deviceClassCalls += 1;
        return [];
      },
    });
    const controller = new MeasureAppController(appState, () => appApi, () => connection(), () => undefined);

    await controller.boot();
    expect(appState.view).toBe("setup");
    expect(catalogCalls).toBe(1);
    expect(appState.lights[0]?.entity_id).toBe("light.desk");
    expect(appState.powers[0]?.entity_id).toBe("sensor.plug_power");
    expect(appState.voltages[0]?.entity_id).toBe("sensor.plug_voltage");
    expect(requestedDomains).toEqual([]);
    expect(deviceClassCalls).toBe(0);

    controller.selectMeasureType("fan");
    expect(appState.selectedMeasureType).toBe("fan");
    await vi.waitFor(() => expect(appState.deviceEntities.fan?.[0]?.entity_id).toBe("fan.bedroom"));
    expect(requestedDomains).toEqual(["fan"]);
  });

  it("retains entity discovery errors and updates session state from the event port", async () => {
    let onEvent: ((event: SessionEvent) => void) | undefined;
    const appState = state();
    const appApi = api({
      getCurrent: async () => ({ state: "running" }),
      getMeasureDefinitions: async () => [{
        measure_type: "fan", label: "Fan", description: "Measure fan power.", supports_profile: true, supports_resume: false,
        fields: [{ name: "fan_entity_id", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      }],
      getEntitiesByDomain: async (domain) => {
        if (domain === "fan") throw new Error("Entity API failed");
        return [];
      },
    });
    const controller = new MeasureAppController(appState, () => appApi, (callbacks) => {
      onEvent = callbacks.onEvent;
      return connection();
    }, () => undefined);

    await controller.boot();
    controller.selectMeasureType("fan");
    await vi.waitFor(() => expect(appState.deviceEntityErrors.fan).toBe("Entity API failed"));

    onEvent?.({ sequence: 1, type: "sample", data: { power: 12.5 }, snapshot: { state: "running" } });
    expect(appState.samples).toEqual([12.5]);
  });

  it("reloads effective capabilities after saving measurement defaults", async () => {
    const appState = state();
    let currentCapabilities = capabilities;
    const controller = new MeasureAppController(appState, () => api({
      getCapabilities: async () => currentCapabilities,
      saveSettings: async (value) => {
        currentCapabilities = {
          ...capabilities,
          defaults: { ...capabilities.defaults, ...value.measurement_defaults },
        };
        return value;
      },
    }), () => connection(), () => undefined);
    await controller.boot();
    controller.openSettings();
    const updated = {
      ...settings,
      measurement_defaults: { ...measurementDefaults, sleep_time: 4, sample_count: 3 },
    };

    await controller.saveSettings(updated);

    expect(appState.capabilities?.defaults.sleep_time).toBe(4);
    expect(appState.capabilities?.defaults.sample_count).toBe(3);
    expect(appState.view).toBe("setup");
  });

  it("reloads the matching dummy-load calibration after changing the power meter", async () => {
    const appState = state();
    let calibrationCalls = 0;
    const controller = new MeasureAppController(appState, () => api({
      getDummyLoadCalibration: async () => {
        calibrationCalls += 1;
        return calibrationCalls === 1 ? null : {
          description: "Heater",
          resistance: 1200,
          calibrated_at: "2026-07-16T11:00:00Z",
        };
      },
    }), () => connection(), () => undefined);
    await controller.boot();
    controller.openSettings();

    await controller.saveSettings({ ...settings, power_meter: "shelly", shelly_ip: "192.0.2.10" });

    expect(calibrationCalls).toBe(2);
    expect(appState.dummyLoadCalibration?.description).toBe("Heater");
  });

  it("retains the previous calibration and can retry after a refresh failure", async () => {
    const appState = state();
    const calibration = {
      description: "Heater",
      resistance: 1200,
      calibrated_at: "2026-07-16T11:00:00Z",
    };
    let calibrationResult: "success" | "failure" = "success";
    const controller = new MeasureAppController(appState, () => api({
      getDummyLoadCalibration: async () => {
        if (calibrationResult === "failure") throw new Error("Calibration API unavailable");
        return calibration;
      },
    }), () => connection(), () => undefined);
    await controller.boot();
    controller.openSettings();
    calibrationResult = "failure";

    await controller.saveSettings(settings);

    expect(appState.dummyLoadCalibration).toEqual(calibration);
    expect(appState.dummyLoadCalibrationError).toContain("Calibration API unavailable");

    calibrationResult = "success";
    await controller.retryDummyLoadCalibration();

    expect(appState.dummyLoadCalibrationError).toBe("");
    expect(appState.dummyLoadCalibration).toEqual(calibration);
  });

  it("ignores a validation result after the meter configuration changes", async () => {
    let resolveValidation: (result: PowerMeterDiagnostic) => void = () => undefined;
    const validation = new Promise<PowerMeterDiagnostic>((resolve) => {
      resolveValidation = resolve;
    });
    const appState = state();
    const controller = new MeasureAppController(
      appState,
      () => api({ testPowerMeter: async () => validation }),
      () => connection(),
      () => undefined,
    );

    const pending = controller.testPowerMeter(settings);
    controller.clearPowerMeterTestResult();
    resolveValidation({
      success: true,
      power: 2.3,
      status: "good",
      precision_decimals: 1,
      max_report_interval_seconds: 1,
      reports_observed: 10,
      duration_seconds: 12,
      precision_status: "good",
      update_interval_status: "good",
      messages: [],
    });
    await pending;

    expect(appState.testingPowerMeter).toBe(false);
    expect(appState.powerMeterTestResult).toBeUndefined();
  });

  it("discovers Shellys when opening Shelly settings and exposes unavailable discovery", async () => {
    const appState = state();
    appState.view = "setup";
    appState.settings = { ...settings, power_meter: "shelly", shelly_ip: "10.0.0.5" };
    const controller = new MeasureAppController(appState, () => api({
      getShellyDevices: async () => ({
        available: false,
        message: "Shelly discovery requires Home Assistant 2025.5 or newer.",
        devices: [{
          id: "shellyplug-s-aabbcc", name: "Shelly Plug S", model: "SHPLG-S", generation: 1,
          ip_address: "10.0.0.5", supported: true, reason: null, auth_required: false,
        }],
      }),
    }), () => connection(), () => undefined);

    controller.openSettings();

    expect(appState.view).toBe("settings");
    expect(appState.discoveringShellys).toBe(true);
    await vi.waitFor(() => expect(appState.discoveringShellys).toBe(false));
    expect(appState.shellyDiscoveryDevices).toHaveLength(1);
    expect(appState.shellyDiscoveryAvailable).toBe(false);
    expect(appState.shellyDiscoveryMessage).toContain("2025.5");
  });

  it("ignores a stale Shelly discovery result after refresh", async () => {
    let resolveFirst: (value: Awaited<ReturnType<MeasureAppApi["getShellyDevices"]>>) => void = () => undefined;
    const first = new Promise<Awaited<ReturnType<MeasureAppApi["getShellyDevices"]>>>((resolve) => { resolveFirst = resolve; });
    let calls = 0;
    const appState = state();
    const controller = new MeasureAppController(appState, () => api({
      getShellyDevices: async () => {
        calls += 1;
        if (calls === 1) return first;
        return { available: true, message: null, devices: [{
          id: "new", name: "New Shelly", model: null, generation: 2,
          ip_address: "10.0.0.8", supported: true, reason: null, auth_required: false,
        }] };
      },
    }), () => connection(), () => undefined);

    const stale = controller.discoverShellys();
    await controller.discoverShellys();
    resolveFirst({ available: true, message: null, devices: [{
      id: "old", name: "Old Shelly", model: null, generation: 1,
      ip_address: "10.0.0.7", supported: true, reason: null, auth_required: false,
    }] });
    await stale;

    expect(appState.shellyDiscoveryDevices.map((device) => device.id)).toEqual(["new"]);
  });
});

function connection(): EventConnection {
  return { connect: () => undefined, close: () => undefined };
}
