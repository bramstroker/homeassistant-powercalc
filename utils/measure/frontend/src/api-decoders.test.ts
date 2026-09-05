import { decodePreflight, isMeasurementRequest } from "./api-decoders";
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
});
