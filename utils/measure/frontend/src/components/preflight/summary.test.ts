import type { MeasureDefinition, MeasurementRequest, PreflightResponse } from "../../types";
import { capabilities, lightDefinition } from "../testing/fixtures";
import { reviewMetrics, reviewSummary } from "./summary";

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

describe("review summary", () => {
  it("restates the recorder purpose, recipe, entity roles, and optional entities", () => {
    const recorder: MeasurementRequest = {
      measure_type: "recorder",
      model_id: "measurement",
      product_name: "Recorder",
      measure_device: "Wall plug",
      generate_model: false,
      parameters: capabilities.defaults,
      power_meter: { type: "hass", entity_id: "sensor.plug_power" },
      resume_policy: "new",
      recorder_purpose: "complex_profile",
      profile_recipe: "vacuum_robot",
      vacuum_entity_id: "vacuum.robot",
      battery_entity_id: "sensor.robot_battery",
      additional_entity_ids: ["sensor.dock_state"],
    };
    const definition: MeasureDefinition = {
      measure_type: "recorder", label: "Recorder", description: "Record states.", icon: "⏺",
      model_id_example: "", product_name_example: "", parameters: [], supports_profile: false, supports_resume: false,
      fields: [
        { name: "recorder_purpose", label: "Purpose", role: "attribute", control: "select", required: true, review: true, options: [{ value: "complex_profile", label: "Data for a complex power profile (experimental)" }] },
        { name: "profile_recipe", label: "Device type", role: "attribute", control: "select", required: true, review: true, options: [{ value: "vacuum_robot", label: "Robot vacuum" }] },
        { name: "vacuum_entity_id", label: "Vacuum", role: "attribute", control: "entity", required: true, review: true, options: [] },
        { name: "battery_entity_id", label: "Battery level sensor", role: "attribute", control: "entity", required: true, review: true, options: [] },
        { name: "additional_entity_ids", label: "Additional entity", plural_label: "Additional entities", role: "attribute", control: "entity", required: false, multiple: true, review: true, options: [] },
      ],
    };

    expect(reviewSummary(recorder, { valid: true, warnings: [] }, definition)).toEqual(expect.arrayContaining([
      { label: "Model", value: "Recorder (measurement)" },
      { label: "Purpose", value: "Data for a complex power profile (experimental)" },
      { label: "Device type", value: "Robot vacuum" },
      { label: "Vacuum", value: "vacuum.robot" },
      { label: "Battery level sensor", value: "sensor.robot_battery" },
      { label: "Additional entity", value: "sensor.dock_state" },
    ]));
  });
});
