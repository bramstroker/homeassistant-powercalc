import { disabledVacuumEntityIds, entityChoices, entityRows, type FieldState } from "./options";
import { recorderDefinition } from "./test-helpers";
import type { EntityDescriptor, MeasurementRequest } from "../../types";
import { capabilities } from "../testing/fixtures";

const entities: EntityDescriptor[] = [
  { entity_id: "vacuum.robot", name: "Robot", domain: "vacuum", device_id: "robot", related_device_ids: ["dock"], state: "docked" },
  { entity_id: "sensor.battery", name: "Battery", domain: "sensor", device_id: "robot", state: "100", unit: "%", device_class: "battery" },
  { entity_id: "sensor.state", name: "State", domain: "sensor", device_id: "robot", state: "idle" },
  { entity_id: "switch.drying", name: "Drying", domain: "switch", device_id: "robot", state: "on" },
  { entity_id: "sensor.unknown", name: "Unknown", domain: "sensor", device_id: "robot", state: "unknown" },
  { entity_id: "sensor.disabled", name: "Disabled", domain: "sensor", device_id: "robot", state: "unavailable", disabled_by: "integration", has_live_state: false },
  { entity_id: "sensor.pending", name: "Pending", domain: "sensor", device_id: "robot", state: "unavailable", has_live_state: false },
  { entity_id: "camera.map", name: "Map", domain: "camera", device_id: "robot", state: "idle" },
  { entity_id: "image.map", name: "Map", domain: "image", device_id: "robot", state: "idle" },
  { entity_id: "sensor.other", name: "Other", domain: "sensor", device_id: "other", state: "idle" },
  { entity_id: "switch.dock_drying", name: "Dock drying", domain: "switch", device_id: "dock", state: "on" },
  { entity_id: "sensor.unassigned", name: "Unassigned", domain: "sensor", state: "idle" },
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
    expect(entityRows(additional, { ...state, selectedEntities: { ...state.selectedEntities, additional_entity_ids: ["switch.dock_drying"] } })).toEqual(["switch.dock_drying"]);
  });

  it("never offers disabled or stateless registry entries as recording choices", () => {
    const choices = entityChoices(additional, state).map((entity) => entity.entity_id);
    expect(choices).not.toContain("sensor.disabled");
    expect(choices).not.toContain("sensor.pending");
    expect(choices).toContain("sensor.state");
  });

  it("only offers entities on the vacuum or its related devices", () => {
    const choices = entityChoices(additional, state).map((entity) => entity.entity_id);
    expect(choices).toContain("sensor.state");
    expect(choices).toContain("switch.dock_drying");
    expect(choices).not.toContain("sensor.other");
    expect(choices).not.toContain("sensor.unassigned");
  });

  it("offers no additional entities without a selected vacuum device", () => {
    expect(entityChoices(additional, { ...state, selectedEntities: {} })).toEqual([]);
    expect(entityChoices(additional, {
      ...state,
      deviceEntities: { "*": entities.map((entity) => entity.entity_id === "vacuum.robot"
        ? { ...entity, device_id: undefined }
        : entity) },
    })).toEqual([]);
  });

  it("only offers same-device entities when the vacuum has no related devices", () => {
    const choices = entityChoices(additional, {
      ...state,
      deviceEntities: { "*": entities.map((entity) => entity.entity_id === "vacuum.robot"
        ? { ...entity, related_device_ids: undefined }
        : entity) },
    }).map((entity) => entity.entity_id);
    expect(choices).toContain("sensor.state");
    expect(choices).not.toContain("switch.dock_drying");
    expect(choices).not.toContain("sensor.other");
  });

  it("excludes the vacuum and its automatically selected battery from additional choices", () => {
    const choices = entityChoices(additional, state).map((entity) => entity.entity_id);
    expect(choices).not.toContain("vacuum.robot");
    expect(choices).not.toContain("sensor.battery");
    expect(choices).toContain("sensor.state");
  });

  it("excludes the chosen battery when several battery sensors exist", () => {
    const otherBattery: EntityDescriptor = {
      ...entities[1]!, entity_id: "sensor.second_battery", name: "Second battery",
    };
    const choices = entityChoices(additional, {
      ...state, deviceEntities: { "*": [...entities, otherBattery] },
      selectedEntities: { ...state.selectedEntities, battery_entity_id: ["sensor.second_battery"] },
    }).map((entity) => entity.entity_id);
    expect(choices).not.toContain("vacuum.robot");
    expect(choices).not.toContain("sensor.second_battery");
    expect(choices).toContain("sensor.battery");
  });

  it("shows useful disabled entities from the selected vacuum and its dock", () => {
    expect(disabledVacuumEntityIds({
      ...state,
      deviceEntities: { "*": entities.map((entity) => entity.domain === "vacuum"
        ? { ...entity, disabled_recording_entity_ids: ["sensor.status", "switch.dock_drying"] }
        : entity) },
    })).toEqual(["sensor.status", "switch.dock_drying"]);
    expect(disabledVacuumEntityIds(state)).toEqual([]);
    expect(disabledVacuumEntityIds({ ...state, selectedEntities: {} })).toEqual([]);
    expect(disabledVacuumEntityIds({ ...state, deviceEntities: {} })).toEqual([]);
    expect(disabledVacuumEntityIds({ ...state, definition: { ...recorderDefinition, fields: [] } })).toEqual([]);
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
