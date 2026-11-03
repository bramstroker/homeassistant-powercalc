import { MeasureAppController, type MeasureAppApi } from "./app-controller";
import type { AppSettings, MeasurementRequest, PowerMeterSpec, PowerMeterDiagnostic, LightMeasurementRequest, CalibrationJob } from "./types";
import { api, capabilities, connection, measurementDefaults, settings, state } from "./testing/controller";

describe("measure app controller: settings", () => {
  const originalRequest: MeasurementRequest = {
    measure_type: "average", duration: 60, model_id: "", product_name: "", session_name: "Desk standby",
    measure_device: "Original meter", power_meter: { type: "hass", entity_id: "sensor.original_power" },
    generate_model: false, parameters: capabilities.defaults, resume_policy: "new",
  };

  it.each<{ label: string; saved: AppSettings; meter: PowerMeterSpec }>([
    {
      label: "a different meter and outlet",
      saved: { ...settings, power_meter: "shelly", shelly_ip: "192.0.2.10", shelly_channel: 3, default_measure_device: "Shelly Power Strip Gen4" },
      meter: { type: "shelly", device_ip: "192.0.2.10", username: "admin", channel: 3 },
    },
    {
      label: "only the measurement-device name",
      saved: { ...settings, default_power_entity_id: "sensor.original_power", default_measure_device: "Renamed meter" },
      meter: { type: "hass", entity_id: "sensor.original_power", voltage_entity_id: null },
    },
    {
      label: "a power sensor with its voltage sensor",
      saved: { ...settings, default_power_entity_id: "sensor.new_power", default_measure_device: "New meter" },
      meter: { type: "hass", entity_id: "sensor.new_power", voltage_entity_id: "sensor.new_voltage" },
    },
    {
      label: "an empty measurement-device name",
      saved: { ...settings, default_power_entity_id: "sensor.original_power", default_measure_device: null },
      meter: { type: "hass", entity_id: "sensor.original_power", voltage_entity_id: null },
    },
  ])("applies $label only to a duplicated session", async ({ saved, meter }) => {
    const appState = state();
    appState.settings = settings;
    const saveSettings = vi.fn(async () => saved);
    const preflight = vi.fn(async () => ({ valid: true, warnings: [] }));
    const controller = new MeasureAppController(appState, () => api({
      getSession: async () => ({ state: "completed", request: originalRequest }),
      saveSettings,
      preflight,
    }), () => connection(), () => undefined);
    await controller.duplicateSession("session-1");
    appState.powers = [{ entity_id: "sensor.new_power", name: "New power", related_voltage_entity_id: "sensor.new_voltage" }];
    controller.openPowerMeterEditor();

    const configuration = { power_meter: meter, measure_device: saved.default_measure_device ?? "" };
    await controller.saveSessionPowerMeter(configuration);

    expect(saveSettings).not.toHaveBeenCalled();
    expect(appState.settings).toBe(settings);
    expect(appState.view).toBe("setup");
    expect(appState.draftPowerMeter).toEqual(configuration);
    expect(appState.request).toEqual(originalRequest);
    expect(originalRequest.power_meter).toEqual({ type: "hass", entity_id: "sensor.original_power" });
    expect(originalRequest.measure_device).toBe("Original meter");
    await controller.preflight({ ...appState.request!, ...appState.draftPowerMeter! });
    expect(preflight).toHaveBeenCalledWith(expect.objectContaining({ power_meter: meter, measure_device: saved.default_measure_device ?? "" }));
  });

  it.each([false, true])("keeps the draft unchanged when global Settings is saved from setup (duplicated=%s)", async (duplicated) => {
    const appState = state();
    appState.settings = { ...settings, default_power_entity_id: "sensor.default", default_measure_device: "Default meter" };
    const saved = { ...settings, power_meter: "kasa" as const, kasa_ip: "192.0.2.20", default_measure_device: "Kasa KP115" };
    const saveSettings = vi.fn(async () => saved);
    const controller = new MeasureAppController(appState, () => api({
      getSession: async () => ({ state: "completed", request: originalRequest }), saveSettings,
    }), () => connection(), () => undefined);
    if (duplicated) await controller.duplicateSession("session-1");
    else controller.newMeasurement();
    const draft = structuredClone(appState.draftPowerMeter);
    const request = appState.request;
    controller.openSettings();

    await controller.saveSettings(saved);

    expect(saveSettings).toHaveBeenCalledWith(saved);
    expect(appState.settings).toEqual(saved);
    expect(appState.draftPowerMeter).toEqual(draft);
    expect(appState.request).toBe(request);
    expect(appState.view).toBe("setup");
    controller.newMeasurement();
    expect(appState.draftPowerMeter).toEqual({ power_meter: { type: "kasa", device_ip: "192.0.2.20" }, measure_device: "Kasa KP115" });
  });

  it.each(["global", "session"])("cancels the %s editor without changing the draft or defaults", (scope) => {
    const appState = state();
    appState.settings = settings;
    appState.request = originalRequest;
    appState.view = "setup";
    const saveSettings = vi.fn();
    const controller = new MeasureAppController(appState, () => api({ saveSettings }), () => connection(), () => undefined);
    if (scope === "session") {
      controller.openPowerMeterEditor();
      controller.closePowerMeterEditor();
    } else {
      controller.openSettings();
      controller.closeSettings();
    }
    expect(appState.request).toBe(originalRequest);
    expect(appState.draftPowerMeter).toEqual({ power_meter: originalRequest.power_meter, measure_device: originalRequest.measure_device });
    expect(appState.settings).toBe(settings);
    expect(appState.view).toBe("setup");
    expect(saveSettings).not.toHaveBeenCalled();
  });

  it("uses the selected session meter and name for measurement and leaves the original recording untouched", async () => {
    const appState = state();
    appState.settings = settings;
    const start = vi.fn(async () => ({ state: "running" as const }));
    const compatible = vi.fn(async () => null);
    const controller = new MeasureAppController(appState, () => api({
      getSession: async () => ({ state: "completed", request: originalRequest }),
      start, getCompatibleCalibration: compatible,
    }), () => connection(), () => undefined);
    await controller.duplicateSession("session-1");
    controller.openPowerMeterEditor();
    const updated = { power_meter: { type: "hass" as const, entity_id: "sensor.other", voltage_entity_id: "sensor.voltage" }, measure_device: "Other meter" };
    await controller.saveSessionPowerMeter(updated);
    expect(compatible).toHaveBeenCalledWith(updated.power_meter);
    controller.openPowerMeterEditor();
    expect(appState.draftPowerMeter).toEqual(updated);
    controller.closePowerMeterEditor();
    await controller.preflight({ ...appState.request!, ...appState.draftPowerMeter! });
    await controller.start();
    expect(start).toHaveBeenCalledWith(expect.objectContaining(updated));
    expect(originalRequest.measure_device).toBe("Original meter");
    expect(originalRequest.power_meter).toEqual({ type: "hass", entity_id: "sensor.original_power" });
  });

  it.each(["running", "result"] as const)("does not open or save the session meter editor from %s", async (view) => {
    const appState = state();
    appState.view = view;
    appState.request = originalRequest;
    const controller = new MeasureAppController(appState, () => api(), () => connection(), () => undefined);
    controller.openPowerMeterEditor();
    await controller.saveSessionPowerMeter({ power_meter: { type: "dummy" }, measure_device: "Dummy" });
    expect(appState.view).toBe(view);
    expect(appState.request).toBe(originalRequest);
  });

  it.each(["running", "result", "profile"] as const)("preserves an existing session when saving settings from %s", async (view) => {
    const appState = state();
    appState.view = view;
    appState.request = originalRequest;
    appState.snapshot = { state: view === "running" ? "running" : "completed", request: originalRequest };
    const controller = new MeasureAppController(appState, () => api(), () => connection(), () => undefined);
    controller.openSettings();

    await controller.saveSettings({ ...settings, power_meter: "kasa", kasa_ip: "192.0.2.20", default_measure_device: "Kasa KP115" });

    expect(appState.view).toBe(view);
    expect(appState.request).toBe(originalRequest);
    expect(appState.snapshot.request).toBe(originalRequest);
  });

  it("keeps the draft and defaults unchanged when saving settings fails", async () => {
    const appState = state();
    appState.view = "setup";
    appState.settings = settings;
    appState.request = originalRequest;
    const controller = new MeasureAppController(appState, () => api({
      saveSettings: async () => { throw new Error("Could not save settings"); },
    }), () => connection(), () => undefined);
    controller.openSettings();

    await controller.saveSettings({ ...settings, power_meter: "kasa", kasa_ip: "192.0.2.20" });

    expect(appState.view).toBe("settings");
    expect(appState.errorMessage).toBe("Could not save settings");
    expect(appState.request).toBe(originalRequest);
    expect(appState.settings).toBe(settings);
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


it("keeps settings calibration scoped to its meter after a standby calibration", async () => {
  const appState = state();
  const calibration = { description: "Session meter heater", resistance: 2300, calibrated_at: "today" };
  const job: CalibrationJob = { id: "job", session_id: "session-1", started_at: "today", status: "completed", calibration, error: null };
  appState.dummyLoadCalibration = calibration;
  appState.dummyLoadCalibrationError = "Old error";
  const changed = vi.fn();
  const controller = new MeasureAppController(appState, () => api({
    calibrateStandby: async () => job,
    getStandbyCalibration: async () => job,
    getDummyLoadCalibration: async () => null,
  }), () => connection(), changed);
  expect(await controller.calibrateStandby("session-1", {} as LightMeasurementRequest)).toEqual(job);
  expect(await controller.getStandbyCalibration("session-1")).toEqual(job);
  expect(appState.dummyLoadCalibration).toBeNull();
  expect(appState.dummyLoadCalibrationError).toBe("");
  expect(changed).toHaveBeenCalledOnce();
});
