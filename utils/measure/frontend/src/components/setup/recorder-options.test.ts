import { disabledVacuumEntityCount, entityChoices, entityRows, type FieldState } from "./options";
import { recorderDefinition } from "./test-helpers";
import type { EntityDescriptor, MeasurementRequest } from "../../types";
import { capabilities } from "../testing/fixtures";

const entities: EntityDescriptor[] = [
  { entity_id: "vacuum.robot", name: "Robot", domain: "vacuum", device_id: "robot", state: "docked" },
  { entity_id: "sensor.battery", name: "Battery", domain: "sensor", device_id: "robot", state: "100", unit: "%", device_class: "battery" },
  { entity_id: "sensor.state", name: "State", domain: "sensor", device_id: "robot", state: "idle" },
  { entity_id: "switch.drying", name: "Drying", domain: "switch", device_id: "robot", state: "on" },
  { entity_id: "sensor.unknown", name: "Unknown", domain: "sensor", device_id: "robot", state: "unknown" },
  { entity_id: "sensor.disabled", name: "Disabled", domain: "sensor", device_id: "robot", state: "unavailable", disabled_by: "integration", has_live_state: false },
  { entity_id: "sensor.pending", name: "Pending", domain: "sensor", device_id: "robot", state: "unavailable", has_live_state: false },
  { entity_id: "camera.map", name: "Map", domain: "camera", device_id: "robot", state: "idle" },
  { entity_id: "image.map", name: "Map", domain: "image", device_id: "robot", state: "idle" },
  { entity_id: "sensor.other", name: "Other", domain: "sensor", device_id: "other", state: "idle" },
];
const additional = recorderDefinition.fields.find((field) => field.name === "additional_entity_ids")!;
const state: FieldState = {
  definition: recorderDefinition, lights: [], deviceEntities: { "*": entities },
  selectedEntities: { vacuum_entity_id: ["vacuum.robot"] },
  selectValues: { recorder_purpose: "complex_profile", profile_recipe: "vacuum_robot" },
  multiSelection: {}, dummyController: false,
};

describe("vacuum recording selection", () => {
  it("starts with no additional entities, even when the vacuum has many", () => {
    const manyEntities = Array.from({ length: 160 }, (_, index) => ({
      entity_id: `sensor.robot_${index}`, name: `Robot ${index}`, domain: "sensor", device_id: "robot", state: "idle",
    }));
    const manyEntityState: FieldState = { ...state, deviceEntities: { "*": [...entities, ...manyEntities] } };
    expect(entityRows(additional, manyEntityState)).toEqual([]);
  });

  it("preserves explicit removals and manual dock selections", () => {
    expect(entityRows(additional, { ...state, selectedEntities: { ...state.selectedEntities, additional_entity_ids: [] } })).toEqual([]);
    expect(entityRows(additional, { ...state, selectedEntities: { ...state.selectedEntities, additional_entity_ids: ["sensor.other"] } })).toEqual(["sensor.other"]);
  });

  it("never offers disabled or stateless registry entries as recording choices", () => {
    const choices = entityChoices(additional, state).map((entity) => entity.entity_id);
    expect(choices).not.toContain("sensor.disabled");
    expect(choices).not.toContain("sensor.pending");
    expect(choices).toContain("sensor.other");
  });

  it("counts only disabled entities on the selected vacuum device", () => {
    expect(disabledVacuumEntityCount({
      ...state,
      deviceEntities: { "*": [...entities, {
        entity_id: "sensor.other_disabled", name: "Other disabled", device_id: "other", disabled_by: "user",
      }] },
    })).toBe(1);
    expect(disabledVacuumEntityCount({ ...state, selectedEntities: {} })).toBe(0);
    expect(disabledVacuumEntityCount({ ...state, deviceEntities: {} })).toBe(0);
    expect(disabledVacuumEntityCount({ ...state, definition: { ...recorderDefinition, fields: [] } })).toBe(0);
  });

  it.each([{ selection: [] }, { selection: ["sensor.other"] }])("preserves persisted additional selections $selection", ({ selection }) => {
    const request: MeasurementRequest = {
      measure_type: "recorder", controller: null, power_meter: { type: "dummy" },
      model_id: "", product_name: "", measure_device: "", generate_model: false,
      parameters: capabilities.defaults, resume_policy: "new", recorder_purpose: "complex_profile", profile_recipe: "vacuum_robot",
      vacuum_entity_id: "vacuum.robot", battery_entity_id: "sensor.battery", additional_entity_ids: selection,
    };
    expect(entityRows(additional, { ...state, request, selectedEntities: {} })).toEqual(selection);
    expect(entityRows(additional, { ...state, request, selectedEntities: { additional_entity_ids: [] } })).toEqual([]);
    expect(entityRows(additional, {
      ...state, request, selectedEntities: { additional_entity_ids: ["sensor.state"] },
    })).toEqual(["sensor.state"]);
  });
});
