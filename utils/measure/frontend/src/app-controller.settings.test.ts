import { MeasureAppController, type MeasureAppApi } from "./app-controller";
import type { PowerMeterDiagnostic } from "./types";
import { api, capabilities, connection, measurementDefaults, settings, state } from "./testing/controller";

describe("measure app controller: settings", () => {
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
    expect(appState.view).toBe("sessions");
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

  it("records the requested settings section so the GitHub shortcut lands on the GitHub tab", () => {
    const appState = state();
    appState.view = "result";
    const controller = new MeasureAppController(appState, () => api(), () => connection(), () => undefined);

    controller.openSettings("github");

    expect(appState.view).toBe("settings");
    expect(appState.settingsSection).toBe("github");
  });

  it("clears the requested settings section when opening settings without a target", () => {
    const appState = state();
    appState.view = "result";
    appState.settingsSection = "github";
    const controller = new MeasureAppController(appState, () => api(), () => connection(), () => undefined);

    controller.openSettings();

    expect(appState.settingsSection).toBeUndefined();
  });

  it("loads canonical measurement-device names without blocking settings", async () => {
    const appState = state();
    appState.view = "setup";
    const controller = new MeasureAppController(appState, () => api({
      getMeasureDevices: async () => ({ devices: ["Shelly Plug S", "TP-Link Kasa KP115"] }),
    }), () => connection(), () => undefined);

    controller.openSettings();

    expect(appState.view).toBe("settings");
    expect(appState.measureDevicesLoading).toBe(true);
    await vi.waitFor(() => expect(appState.measureDevicesLoading).toBe(false));
    expect(appState.measureDevices).toEqual(["Shelly Plug S", "TP-Link Kasa KP115"]);
    expect(appState.measureDevicesError).toBe("");
  });

  it("keeps settings usable when measurement-device suggestions fail", async () => {
    const appState = state();
    appState.view = "setup";
    const controller = new MeasureAppController(appState, () => api({
      getMeasureDevices: async () => { throw new Error("Library unavailable"); },
    }), () => connection(), () => undefined);

    controller.openSettings();

    await vi.waitFor(() => expect(appState.measureDevicesLoading).toBe(false));
    expect(appState.view).toBe("settings");
    expect(appState.measureDevices).toEqual([]);
    expect(appState.measureDevicesError).toBe("Library unavailable");
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
