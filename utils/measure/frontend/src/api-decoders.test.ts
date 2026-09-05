import { decodePreflight, decodeSessionSnapshot, isMeasurementRequest } from "./api-decoders";
import { capabilities } from "./components/testing/fixtures";

const averageRequest = {
  measure_type: "average",
  model_id: "",
  product_name: "",
  session_name: "Average power",
  measure_device: "",
  power_meter: { type: "dummy" },
  generate_model: false,
  parameters: capabilities.defaults,
  resume_policy: "new",
  duration: 60,
  controller: null,
};

describe("measurement request boundary", () => {
  it("accepts a complete request built by the frontend", () => {
    expect(isMeasurementRequest(averageRequest)).toBe(true);
  });

  it("rejects invalid numeric and discriminated values", () => {
    expect(isMeasurementRequest({ ...averageRequest, duration: Number.NaN })).toBe(false);
    expect(isMeasurementRequest({ ...averageRequest, duration: 1.5 })).toBe(false);
    expect(isMeasurementRequest({ ...averageRequest, resume_policy: "continue" })).toBe(false);
    expect(isMeasurementRequest({
      ...averageRequest,
      power_meter: { type: "hass" },
    })).toBe(false);
  });

  it("requires the resistance carried by a reused dummy-load calibration", () => {
    expect(isMeasurementRequest({
      ...averageRequest,
      dummy_load: { mode: "reuse", description: "60 W incandescent bulb" },
    })).toBe(false);
    expect(isMeasurementRequest({
      ...averageRequest,
      dummy_load: { mode: "reuse", description: "60 W incandescent bulb", resistance: 882.4 },
    })).toBe(true);
  });

  it("does not accept a controller variant for the wrong measurement type", () => {
    expect(isMeasurementRequest({
      ...averageRequest,
      measure_type: "fan",
      controller: { type: "hue", bridge_ip: "192.0.2.10", light: "1" },
    })).toBe(false);
  });
});

describe("response boundary", () => {
  it("accepts nullable estimates emitted by an incomplete preflight", () => {
    const response = {
      valid: true,
      warnings: [],
      estimated_variations: null,
      estimated_duration_seconds: null,
      supported_modes: null,
      power_meter_diagnostic: null,
      battery_level_entity_id: null,
      battery_level_attribute: null,
      light_load_probe: null,
    };

    expect(decodePreflight(response)).toBe(response);
  });

  it("requires the recorder-analysis capability flag on session snapshots", () => {
    const response = {
      session_id: "session-1",
      state: "completed",
      can_analyse: true,
      created_at: "2026-09-05T10:00:00Z",
      updated_at: "2026-09-05T10:05:00Z",
      phase: null,
      confirmation_message: null,
      confirmation_action: null,
      mode: null,
      progress: { completed: 1, total: 1, skipped: 0, percent: 100, estimated_remaining_seconds: 0 },
      warnings: [],
      error: null,
      summary: null,
      request: averageRequest,
      operating_point: null,
      calibration_sample: null,
      entity_states: {},
    };

    expect(decodeSessionSnapshot(response)).toBe(response);
    const { can_analyse: _missing, ...withoutCapability } = response;
    expect(() => decodeSessionSnapshot(withoutCapability)).toThrow("Invalid session snapshot response");
    expect(() => decodeSessionSnapshot({ ...response, can_analyse: "yes" })).toThrow("Invalid session snapshot response");
  });
});
