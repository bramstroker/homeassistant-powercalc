import { ApiError } from "./api-client";
import { MeasureAppController } from "./app-controller";
import { api, capabilities, connection, state } from "./testing/controller";

describe("measure app controller: navigation", () => {
  it.each(["snapshot", "request"] as const)("prevents profile navigation for average measurements from %s", (source) => {
    const appState = state();
    const request = {
      measure_type: "average" as const, duration: 60, model_id: "", product_name: "", measure_device: "Test meter",
      generate_model: false, parameters: capabilities.defaults, resume_policy: "new" as const, power_meter: { type: "dummy" as const },
    };
    appState.view = "result";
    appState.snapshot = { state: "completed", ...(source === "snapshot" ? { request } : {}) };
    if (source === "request") appState.request = request;
    const controller = new MeasureAppController(appState, () => api(), () => connection(), () => undefined);
    controller.openProfile();
    expect(appState.view).toBe("result");
    controller.openShare();
    expect(appState.view).toBe("result");
    controller.backToProfile();
    expect(appState.view).toBe("result");
  });

  it("preserves structured help from API errors", async () => {
    const appState = state();
    const help = {
      url: "https://docs.powercalc.nl/contributing/measure/low-power-measurements/",
      label: "Low-power measurement guide",
    };
    const controller = new MeasureAppController(appState, () => api({
      preflight: async () => { throw new ApiError("The meter repeatedly returned 0 W.", 422, "preflight_failed", null, help); },
    }), () => connection(), () => undefined);

    await controller.preflight({
      measure_type: "average",
      duration: 1,
      model_id: "",
      product_name: "",
      measure_device: "",
      generate_model: false,
      parameters: capabilities.defaults,
      resume_policy: "new",
      power_meter: { type: "dummy" },
    });

    expect(appState.errorMessage).toBe("The meter repeatedly returned 0 W.");
    expect(appState.errorHelp).toEqual(help);

    controller.backToSetup();
    expect(appState.errorHelp).toBeUndefined();
  });

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

    expect(appState.view).toBe("sessions");
    expect(appState.dummyLoadCalibration).toBeNull();
    expect(appState.dummyLoadCalibrationError).toContain("Calibration API unavailable");
  });


});
