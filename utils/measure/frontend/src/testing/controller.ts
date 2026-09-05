import type { EventConnection, MeasureAppApi, MeasureAppState } from "../app-controller";
import type { SessionSummary } from "../types";

export const measurementDefaults = { sleep_time: 1, sample_count: 2, sleep_time_sample: 1, max_retries: 5, max_nudges: 0 };
export const settings = {
  default_power_entity_id: null, default_measure_device: null, power_meter: "hass" as const, shelly_ip: null, kasa_ip: null,
  fast_test_mode: false,
  measurement_defaults: measurementDefaults,
};
export const capabilities = {
  runtime_version: "v0.2.1:app",
  modes: ["brightness" as const],
  defaults: {
    ...measurementDefaults,
    bri_bri_steps: 1, ct_bri_steps: 5, ct_mired_steps: 10,
    hs_bri_steps: 32, hs_hue_steps: 2731, hs_sat_steps: 32,
    min_brightness: 1, sleep_initial: 10, sleep_standby: 20,
    effect_bri_steps: 40, measure_time_effect: 180, measure_time_effect_min: 20,
  },
};

export function sessionSummary(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    session_id: "session-1",
    state: "completed",
    created_at: "2026-08-13T10:00:00Z",
    updated_at: "2026-08-13T10:05:00Z",
    measure_type: "light",
    model_id: "LCT010",
    product_name: "Hue lamp",
    measure_device: "Desk lamp",
    completed: 1,
    total: 1,
    percent: 100,
    can_resume: false,
    file_count: 1,
    size: 10,
    active: false,
    ...overrides,
  };
}

export function state(): MeasureAppState {
  return {
    view: "loading", errorMessage: "", busy: false, connectedToEvents: false,
    sessions: [],
    files: [], plotCollection: { partial: false, plots: [], warnings: [] },
    logs: [], samples: [], lights: [], powers: [], voltages: [], definitions: [],
    dummyLoadCalibration: null, dummyLoadCalibrationError: "",
    measureDevices: [], measureDevicesLoading: false, measureDevicesError: "",
    deviceSpecificationFields: {},
    contributionBusy: false, contributionAuthBusy: false, contributionError: "", contributionAuthError: "",
    deviceEntities: {}, deviceEntityErrors: {}, testingPowerMeter: false,
    shellyDiscoveryDevices: [], discoveringShellys: false, shellyDiscoveryError: "",
  };
}

export function api(overrides: Partial<MeasureAppApi> = {}): MeasureAppApi {
  return {
    getCapabilities: async () => capabilities,
    getMeasureDefinitions: async () => [],
    getMeasureDevices: async () => ({ devices: [] }),
    getManufacturers: async () => ({ manufacturers: [] }),
    getDeviceSpecifications: async () => ({ device_types: {} }),
    getSettings: async () => settings,
    getContributionAuth: async () => ({ connected: false }),
    getContributionStatus: async () => ({ state: "idle" as const }),
    startContributionDeviceAuth: async () => ({
      flow_id: "flow-1",
      user_code: "ABCD-EFGH",
      verification_uri: "https://github.com/login/device",
      expires_in: 900,
      interval: 5,
    }),
    getContributionDeviceAuth: async () => ({ status: "pending" }),
    saveContributionToken: async () => ({ connected: true, method: "token", identity: { login: "octocat" } }),
    disconnectContributionAuth: async () => ({ connected: false }),
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
    getAllEntities: async () => [],
    getEntityCatalog: async () => ({ lights: [], powers: [], voltages: [] }),
    getEntitiesByDomain: async () => [],
    getEntitiesByDeviceClass: async () => [],
    getDummyLoadCalibration: async () => null,
    preflight: async () => ({ valid: true, warnings: [] }),
    start: async () => ({ state: "running" }),
    getSessions: async () => [],
    getSession: async () => ({ state: "idle" }),
    deleteSession: async () => undefined,
    cancel: async () => ({ state: "cancelled" }),
    confirm: async () => ({ state: "running" }),
    resume: async () => ({ state: "running" }),
    getFiles: async () => [],
    getPlots: async () => ({ partial: false, plots: [], warnings: [] }),
    getContributionDraft: async () => ({
      eligible: false,
      reason: "No profile output",
      repository: "bramstroker/homeassistant-powercalc",
      base_branch: "master",
      manufacturer_name: "",
      manufacturer_directory: "",
      model_id: "",
      product_name: "",
      contributor: "",
      device_info: {},
      home_assistant: {},
      notes: "",
      files: [],
      commit_message: "",
      pr_title: "",
      pr_body: "",
      branch_name: "",
      warnings: [],
    }),
    previewContribution: async (_sessionId, request) => ({
      eligible: true,
      repository: "bramstroker/homeassistant-powercalc",
      base_branch: "master",
      manufacturer_name: request.manufacturer_name,
      manufacturer_directory: "signify",
      model_id: request.model_id,
      product_name: request.product_name,
      contributor: request.contributor,
      device_info: {},
      home_assistant: {},
      notes: request.notes,
      files: [],
      commit_message: "Add measured profile",
      pr_title: "Add measured profile",
      pr_body: "",
      branch_name: "measure/profile",
      warnings: [],
    }),
    submitContribution: async () => ({ status: "success", pull_request_url: "https://github.com/pull/1" }),
    ...overrides,
  };
}

export function connection(): EventConnection {
  return { connect: () => undefined, close: () => undefined };
}
