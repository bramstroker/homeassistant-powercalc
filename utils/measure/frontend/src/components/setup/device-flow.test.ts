import type { MeasureDefinition, MeasurementRequest } from "../../types";
import "./view";
import { capabilities, lightDefinition, type SetupViewElement } from "../testing/fixtures";
import { entityCombobox, recorderDefinition, selectEntity } from "./test-helpers";

const camera = {
  entity_id: "camera.porch", name: "Porch camera", domain: "camera", state: "idle", device_id: "porch",
};
const mode = {
  entity_id: "sensor.porch_mode", name: "Porch mode", domain: "sensor", state: "night", device_id: "porch",
};

function createSetup(): SetupViewElement {
  const element = document.createElement("measure-setup-view") as SetupViewElement;
  element.capabilities = capabilities;
  element.definitions = [lightDefinition, recorderDefinition];
  element.deviceEntities = { "*": [camera, mode] };
  element.meter = { type: "dummy" };
  document.body.append(element);
  return element;
}

afterEach(() => document.body.replaceChildren());

describe("device-first setup", () => {
  it("filters device types and opens the only light route directly", async () => {
    const element = createSetup();
    await element.updateComplete;
    const search = element.shadowRoot.querySelector<HTMLInputElement>('input[type="search"]')!;
    search.value = "camera";
    search.dispatchEvent(new Event("input"));
    await element.updateComplete;
    expect([...element.shadowRoot.querySelectorAll(".device-card")].map((card) => card.querySelector(".type-label")?.textContent))
      .toEqual(["Camera"]);
    search.value = "";
    search.dispatchEvent(new Event("input"));
    await element.updateComplete;
    [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".device-card")]
      .find((card) => card.querySelector(".type-label")?.textContent === "Light")!.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector("form")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".route-card")).toBeNull();
    expect(element.shadowRoot.textContent).toContain("Automated light measurement");
  });

  it("submits the device and recorder recipe selected in the entry flow", async () => {
    const element = createSetup();
    await element.updateComplete;
    [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".device-card")]
      .find((card) => card.querySelector(".type-label")?.textContent === "Camera")!.click();
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="recorder_purpose"]')).toBeNull();
    expect(element.shadowRoot.querySelector('select[name="profile_device_type"]')).toBeNull();
    expect(element.shadowRoot.querySelector(".type-chip .device-icon")?.textContent).toBe("📷");
    selectEntity(entityCombobox(element, "primary_entity_id"), camera.entity_id);
    await element.updateComplete;
    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    element.shadowRoot.querySelector<HTMLFormElement>("form")!.requestSubmit();
    expect(await submitted).toMatchObject({
      measure_type: "recorder", recorder_purpose: "complex_profile", profile_recipe: "generic",
      profile_device_type: "camera", primary_entity_id: "camera.porch",
    });
  });

  it("restores a saved generic recording in the matching device route", async () => {
    const element = createSetup();
    element.initialRequest = {
      measure_type: "recorder", controller: null, model_id: "", product_name: "", measure_device: "",
      power_meter: { type: "dummy" }, generate_model: true, parameters: capabilities.defaults, resume_policy: "new",
      recorder_purpose: "complex_profile", profile_recipe: "generic", profile_device_type: "camera",
      primary_entity_id: "camera.porch", tracked_entity_ids: ["sensor.porch_mode"],
    };
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".type-chip")?.textContent).toContain("Camera");
    expect(entityCombobox(element, "primary_entity_id").value).toBe(camera.entity_id);
    expect(entityCombobox(element, "tracked_entity_ids").value).toEqual([mode.entity_id]);
    expect(element.shadowRoot.querySelector('input[name="profile_device_type"]')).toHaveProperty("value", "camera");
  });

  it("keeps an older light recording editable while offering only automated light measurement to new sessions", async () => {
    const element = createSetup();
    element.definitions = [lightDefinition, {
      ...recorderDefinition,
      fields: recorderDefinition.fields.map((field) => field.name === "profile_device_type"
        ? { ...field, options: [...field.options, { value: "light", label: "Light", entity_domains: ["light"] }] }
        : field),
    }];
    element.initialRequest = {
      measure_type: "recorder", controller: null, model_id: "", product_name: "", measure_device: "",
      power_meter: { type: "dummy" }, generate_model: true, parameters: capabilities.defaults, resume_policy: "new",
      recorder_purpose: "complex_profile", profile_recipe: "generic", profile_device_type: "light",
      primary_entity_id: "light.old", tracked_entity_ids: [],
    };
    await element.updateComplete;
    expect(element.shadowRoot.querySelector("form")).toBeTruthy();
    expect(element.shadowRoot.querySelector('input[name="profile_device_type"]')).toHaveProperty("value", "light");

    (element.shadowRoot.querySelector(".selection-actions button") as HTMLButtonElement).click();
    await element.updateComplete;
    [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".device-card")]
      .find((card) => card.querySelector(".type-label")?.textContent === "Light")!.click();
    await element.updateComplete;
    expect(element.selectedType).toBe("light");
    expect(element.shadowRoot.querySelector(".route-card")).toBeNull();
  });

  it("returns from the form to the device list and discards route-specific choices", async () => {
    const element = createSetup();
    await element.updateComplete;
    [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".device-card")]
      .find((card) => card.querySelector(".type-label")?.textContent === "Camera")!.click();
    await element.updateComplete;
    selectEntity(entityCombobox(element, "primary_entity_id"), camera.entity_id);
    await element.updateComplete;
    (element.shadowRoot.querySelector(".type-chip button") as HTMLButtonElement).click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector("form")).toBeNull();
    expect(element.shadowRoot.querySelector(".device-card")).toBeTruthy();
    expect(element.selectedEntities).toEqual({});
  });

  it("asks for a method when a device has two routes and clears the old route", async () => {
    const element = createSetup();
    const fan: MeasureDefinition = { ...lightDefinition, measure_type: "fan", label: "Fan" };
    const recorder: MeasureDefinition = {
      ...recorderDefinition,
      fields: recorderDefinition.fields.map((field) => field.name === "profile_device_type"
        ? { ...field, options: [...field.options, { value: "fan", label: "Fan", entity_domains: ["fan"] }] }
        : field),
    };
    element.definitions = [fan, recorder];
    await element.updateComplete;
    [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".device-card")]
      .find((card) => card.querySelector(".type-label")?.textContent === "Fan")!.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelectorAll(".route-card")).toHaveLength(2);
    expect(element.shadowRoot.querySelector("form")).toBeNull();

    [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".route-card")]
      .find((card) => card.textContent?.includes("Record device states"))!.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector('input[name="profile_device_type"]')).toHaveProperty("value", "fan");
    element.selectedEntities = { primary_entity_id: ["fan.old"] };
    (element.shadowRoot.querySelector(".selection-actions button") as HTMLButtonElement).click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelectorAll(".route-card")).toHaveLength(2);
    expect(element.selectedEntities).toEqual({});
    [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".route-card")]
      .find((card) => card.textContent?.includes("Measure fan speeds"))!.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector('input[name="profile_device_type"]')).toBeNull();
    expect(element.selectedType).toBe("fan");
  });
});
