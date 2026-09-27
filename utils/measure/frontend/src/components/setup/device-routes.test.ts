import type { MeasureDefinition, MeasurementRequest } from "../../types";
import { lightDefinition } from "../testing/fixtures";
import { recorderDefinition } from "./test-helpers";
import { deviceChoices, FREE_MEASUREMENT, routesForDevice, selectionFromRequest } from "./device-routes";

const speaker: MeasureDefinition = { ...lightDefinition, measure_type: "speaker", label: "Smart speaker" };
const fan: MeasureDefinition = { ...lightDefinition, measure_type: "fan", label: "Fan" };
const charging: MeasureDefinition = {
  ...lightDefinition,
  measure_type: "charging",
  label: "Charging device",
  fields: [{
    name: "charging_device_type", label: "Charging device type", control: "select", role: "attribute",
    required: true, options: [
      { value: "vacuum_robot", label: "Vacuum robot" },
      { value: "lawn_mower_robot", label: "Lawn mower robot" },
    ],
  }],
};
const average: MeasureDefinition = { ...lightDefinition, measure_type: "average", label: "Average" };
const recorder: MeasureDefinition = {
  ...recorderDefinition,
  fields: recorderDefinition.fields.map((field) => field.name === "profile_device_type" ? {
    ...field,
    options: [
      ...field.options,
      { value: "air_conditioner", label: "Air conditioner", entity_domains: ["climate"] },
      { value: "fan", label: "Fan", entity_domains: ["fan"] },
      { value: "smart_speaker", label: "Smart speaker", entity_domains: ["media_player"] },
      { value: "lawn_mower_robot", label: "Lawn mower robot", entity_domains: ["lawn_mower"] },
    ],
  } : field),
};
const definitions = [lightDefinition, speaker, fan, charging, recorder, average];

describe("device-first measurement routes", () => {
  it("lists server-supported profile types and a dedicated vacuum, without duplicating specialist types", () => {
    const choices = deviceChoices(definitions);
    expect(choices.map((choice) => choice.id)).toEqual([
      "camera", "fan", "generic_iot", "heating", "lawn_mower_robot", "light",
      "vacuum_robot", "smart_speaker", "smart_switch",
    ]);
    expect(choices.filter((choice) => choice.id === "vacuum_robot")).toHaveLength(1);
    expect(choices.find((choice) => choice.id === "camera")?.experimental).toBe(true);
    expect(choices.find((choice) => choice.id === "light")?.experimental).toBe(false);
    expect(choices.find((choice) => choice.id === "vacuum_robot")?.experimental).toBe(true);
    expect(choices.find((choice) => choice.id === "lawn_mower_robot")?.experimental).toBe(true);
    expect(choices.find((choice) => choice.id === "fan")?.experimental).toBe(true);
  });

  it("offers only the automated measurement for lights", () => {
    expect(routesForDevice("light", definitions).map((route) => route.id)).toEqual(["light"]);
    expect(routesForDevice("light", definitions.filter((item) => item.measure_type !== "light"))).toEqual([]);
  });

  it("offers only automated measurement for smart speakers", () => {
    expect(routesForDevice("smart_speaker", definitions).map((route) => route.id)).toEqual(["speaker"]);
    expect(routesForDevice("smart_speaker", definitions.filter((item) => item.measure_type !== "speaker"))).toEqual([]);
  });

  it("offers specialist and recorder routes where both exist", () => {
    expect(routesForDevice("fan", definitions).map((route) => route.id)).toEqual(["fan", "complex_profile"]);
    expect(routesForDevice("vacuum_robot", definitions).map((route) => route.id)).toEqual(["vacuum_profile", "charging"]);
    expect(routesForDevice("lawn_mower_robot", definitions).map((route) => route.id)).toEqual(["charging", "complex_profile"]);
    expect(routesForDevice("camera", definitions)[0]?.preset).toEqual({
      recorder_purpose: "complex_profile", profile_recipe: "generic", profile_device_type: "camera",
    });
    expect(routesForDevice("vacuum_robot", definitions)[0]?.preset).toEqual({
      recorder_purpose: "complex_profile", profile_recipe: "vacuum_robot",
    });
    expect(routesForDevice("vacuum_robot", definitions)[0]?.recommended).toBe(true);
    expect(routesForDevice("vacuum_robot", definitions)[0]?.experimental).toBe(true);
    expect(routesForDevice("fan", definitions)[1]?.experimental).toBe(true);
  });

  it("keeps average and Playbook under free measurement", () => {
    expect(routesForDevice(FREE_MEASUREMENT, definitions).map((route) => route.id)).toEqual(["average", "playbook"]);
    expect(routesForDevice("camera", definitions).map((route) => route.id)).not.toContain("playbook");
  });

  it("restores old requests to their device and route", () => {
    const base = {
      model_id: "", product_name: "", measure_device: "", generate_model: false,
      parameters: {}, resume_policy: "new", power_meter: { type: "dummy" },
    };
    const restore = (values: Record<string, unknown>) => selectionFromRequest({ ...base, ...values } as MeasurementRequest);
    expect(restore({ measure_type: "average", duration: 60 })).toEqual({ deviceId: FREE_MEASUREMENT, routeId: "average" });
    expect(restore({ measure_type: "recorder", recorder_purpose: "playbook" })).toEqual({ deviceId: FREE_MEASUREMENT, routeId: "playbook" });
    expect(restore({ measure_type: "recorder", recorder_purpose: "complex_profile", profile_recipe: "vacuum_robot" }))
      .toEqual({ deviceId: "vacuum_robot", routeId: "vacuum_profile" });
    expect(restore({ measure_type: "recorder", recorder_purpose: "complex_profile", profile_recipe: "generic", profile_device_type: "camera" }))
      .toEqual({ deviceId: "camera", routeId: "complex_profile" });
    expect(restore({ measure_type: "charging", charging_device_type: "lawn_mower_robot" }))
      .toEqual({ deviceId: "lawn_mower_robot", routeId: "charging" });
  });
});
