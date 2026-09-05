import { MeasureAppController } from "./app-controller";
import { api, connection, state } from "./testing/controller";

describe("measure app controller: sessions", () => {
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
      getSession: async () => ({ state: "cancelled", session_id: "session-1" }),
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
    await controller.openSession("session-1");

    expect(appState.view).toBe("result");
    expect(appState.files).toHaveLength(1);
    expect(appState.plotCollection).toEqual(plots);
    expect(appState.dummyLoadCalibration?.description).toBe("Calibrated load");
  });

  it("loads contribution auth and draft data for a completed session", async () => {
    const appState = state();
    const controller = new MeasureAppController(appState, () => api({
      getSession: async () => ({ state: "completed", session_id: "session-1" }),
      getContributionAuth: async () => ({ connected: true, identity: { login: "octocat" }, method: "device" }),
      getManufacturers: async () => ({ manufacturers: ["IKEA", "Signify"] }),
      getMeasureDevices: async () => ({ devices: ["Shelly Plug S", "Kasa EP25"] }),
      getDeviceSpecifications: async () => ({
        device_types: {
          light: [{ name: "rated_power", label: "Rated power", description: "Rated watts", value_type: "number", collection: "scalar", options: [] }],
        },
      }),
      getContributionDraft: async () => ({
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
        notes: "Measured from HA app",
        files: [{ path: "profile_library/signify/LCT010/model.json", rendered_json: { name: "Hue lamp" } }],
        model_json: { name: "Hue lamp" },
        commit_message: "Add Signify LCT010",
        pr_title: "Add Signify LCT010",
        pr_body: "Adds a measured profile.",
        branch_name: "measure/signify-lct010",
        warnings: [],
      }),
    }), () => connection(), () => undefined);

    await controller.boot();
    await controller.openSession("session-1");

    expect(appState.view).toBe("result");
    expect(appState.contributionAuth?.identity?.login).toBe("octocat");
    expect(appState.contributionDraft?.files[0]?.path).toBe("profile_library/signify/LCT010/model.json");
    expect(appState.manufacturers).toEqual(["IKEA", "Signify"]);
    expect(appState.measureDevices).toEqual(["Shelly Plug S", "Kasa EP25"]);
    expect(appState.deviceSpecificationFields.light?.[0]?.name).toBe("rated_power");
    expect(appState.contributionPreview).toBeUndefined();
  });

  it("restores a persisted submitted contribution for the current session", async () => {
    const appState = state();
    const controller = new MeasureAppController(appState, () => api({
      getSession: async () => ({ state: "completed", session_id: "session-1" }),
      getContributionStatus: async () => ({
        state: "submitted" as const,
        session_id: "session-1",
        submission_url: "https://github.com/pull/9",
        message: "Contribution submitted",
      }),
    }), () => connection(), () => undefined);

    await controller.boot();
    await controller.openSession("session-1");

    expect(appState.contributionResult?.pull_request_url).toBe("https://github.com/pull/9");
    expect(appState.contributionResult?.status).toBe("success");
  });

  it("ignores persisted contribution status from another session", async () => {
    const appState = state();
    const controller = new MeasureAppController(appState, () => api({
      getSession: async () => ({ state: "completed", session_id: "session-2" }),
      getContributionStatus: async () => ({
        state: "failed" as const,
        session_id: "session-1",
        error: "Old failure",
      }),
    }), () => connection(), () => undefined);

    await controller.boot();
    await controller.openSession("session-2");

    expect(appState.contributionResult).toBeUndefined();
    expect(appState.contributionError).toBe("");
  });

  it("analyses a saved recording again and refreshes its result artifacts", async () => {
    const appState = state();
    appState.view = "result";
    appState.snapshot = { state: "completed", session_id: "session-1", can_analyse: true };
    const analyse = vi.fn(async () => ({
      state: "completed" as const,
      session_id: "session-1",
      can_analyse: true,
      summary: { "Recording analysis": "Fixed power profile created" },
    }));
    const getFiles = vi.fn(async () => [{ name: "model.json", size: 10, media_type: "application/json" }]);
    const controller = new MeasureAppController(appState, () => api({ analyse, getFiles }), () => connection(), () => undefined);

    await controller.analyseRecording();

    expect(analyse).toHaveBeenCalledWith("session-1");
    expect(appState.snapshot.summary?.["Recording analysis"]).toBe("Fixed power profile created");
    expect(getFiles).toHaveBeenCalledWith("session-1");
    expect(appState.files).toHaveLength(1);
    expect(appState.lastAnalysedSessionId).toBe("session-1");
    expect(appState.view).toBe("result");
    expect(appState.busy).toBe(false);
  });


});
