import type { MeasurementRequest, PreflightResponse } from "./types";
import { reviewMetrics } from "./review-summary";
import { capabilities, lightDefinition } from "./components/test-fixtures";

const request: MeasurementRequest = {
  measure_type: "light",
  model_id: "test",
  product_name: "Test light",
  measure_device: "Test meter",
  generate_model: true,
  parameters: capabilities.defaults,
  power_meter: { type: "hass", entity_id: "sensor.plug_power" },
  controller: { type: "hass", entity_id: "light.test" },
  modes: ["hs"],
  gzip: true,
  multiple_light_count: 1,
  resume_policy: "new",
};

describe("review metrics", () => {
  it("adds active low-load probe results to the review metrics", () => {
    const preflight: PreflightResponse = {
      valid: true,
      warnings: [],
      light_load_probe: {
        checked_variations: 3,
        minimum_aggregate_power_w: 0.9,
        points: [
          { label: "Color 0° / 100% saturation · brightness 1", mode: "hs", power_w: 1.2 },
          { label: "Color 120° / 100% saturation · brightness 1", mode: "hs", power_w: 0.9 },
          { label: "Color 240° / 100% saturation · brightness 1", mode: "hs", power_w: 1.1 },
        ],
      },
    };

    const metrics = reviewMetrics(request, preflight, lightDefinition);

    expect(metrics).toContainEqual({ label: "Low-load checks", value: "3" });
    expect(metrics).toContainEqual({ label: "Lowest aggregate load", value: "0.900 W" });
  });

  it("omits the probe metrics when preflight did not run one", () => {
    const metrics = reviewMetrics(request, { valid: true, warnings: [] }, lightDefinition);

    expect(metrics.map((metric) => metric.label)).not.toContain("Low-load checks");
  });
});
