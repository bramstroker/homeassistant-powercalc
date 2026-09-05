import type { MeasurementRequest } from "../../types";
import "./view";
import { SetupViewElement, capabilities, lightDefinition, lights } from "../testing/fixtures";
import type { TestCombobox } from "./test-helpers";
import { entityCombobox, recorderDefinition, selectEntity } from "./test-helpers";

describe("setup view defaults", () => {
  it("restores a duplicated recorder request with its persisted null controller", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [recorderDefinition];
    element.deviceEntities = {
      "*": [{ entity_id: "climate.room", name: "Room", domain: "climate", state: "heat" }],
    };
    element.selectedType = "recorder";
    element.initialRequest = {
      measure_type: "recorder",
      controller: null,
      model_id: "measurement",
      product_name: "Recorder",
      measure_device: "",
      power_meter: { type: "dummy" },
      generate_model: false,
      parameters: capabilities.defaults,
      resume_policy: "new",
      recorder_purpose: "complex_profile",
      profile_recipe: "generic",
      tracked_entity_ids: ["climate.room"],
      export_filename: "record.jsonl",
    };
    element.meter = { type: "dummy" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('[name="recorder_purpose"]')).toBeTruthy();
    expect(element.shadowRoot.querySelector('[name="profile_recipe"]')).toBeTruthy();
    const trackedEntity = entityCombobox(element, "tracked_entity_ids");
    expect(trackedEntity).toBeTruthy();
    expect((trackedEntity.querySelector('input[slot="value"]') as HTMLInputElement).value).toBe("climate.room");
  });

  it("starts the recorder with a purpose choice and reveals the generic recipe conditionally", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [recorderDefinition];
    element.deviceEntities = { "*": [] };
    element.selectedType = "recorder";
    element.meter = { type: "dummy" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('[name="recorder_purpose"]')).toBeTruthy();
    expect(element.shadowRoot.querySelector('[name="profile_recipe"]')).toBeNull();
    expect(element.shadowRoot.querySelector('[name="tracked_entity_ids"]')).toBeNull();
    expect(element.shadowRoot.textContent).toContain("Record the playbook format");

    const requestedDomains = new Promise<string[]>((resolve) => {
      element.addEventListener("entity-domains-requested", (event) => resolve((event as CustomEvent<string[]>).detail));
    });
    selectEntity(entityCombobox(element, "recorder_purpose"), "complex_profile");
    await element.updateComplete;

    expect(await requestedDomains).toContain("*");
    expect(element.shadowRoot.querySelector('[name="profile_recipe"]')).toBeTruthy();
    expect(element.shadowRoot.querySelector('[name="tracked_entity_ids"]')).toBeTruthy();
    expect(element.shadowRoot.textContent).toContain("not feature complete");
    expect(element.shadowRoot.textContent).toContain("does not create a profile model.json yet");
    expect((element.shadowRoot.querySelector('[name="export_filename"]') as HTMLInputElement).value).toBe("record.jsonl");
  });

  it("guides a vacuum selection and prefills its single same-device battery sensor", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [recorderDefinition];
    element.deviceEntities = { "*": [
      { entity_id: "vacuum.robot", name: "Robot", domain: "vacuum", device_id: "robot-device", state: "docked" },
      { entity_id: "sensor.robot_battery", name: "Robot battery", domain: "sensor", device_id: "robot-device", device_class: "battery", state: "42", unit: "%" },
      { entity_id: "sensor.other_battery", name: "Other battery", domain: "sensor", device_id: "other-device", device_class: "battery", state: "80", unit: "%" },
      { entity_id: "sensor.dock_state", name: "Dock state", domain: "sensor", device_id: "robot-device", state: "idle" },
    ] };
    element.selectedType = "recorder";
    element.meter = { type: "dummy" };
    document.body.append(element);
    await element.updateComplete;

    selectEntity(entityCombobox(element, "recorder_purpose"), "complex_profile");
    await element.updateComplete;
    selectEntity(entityCombobox(element, "profile_recipe"), "vacuum_robot");
    await element.updateComplete;
    selectEntity(entityCombobox(element, "vacuum_entity_id"), "vacuum.robot");
    await element.updateComplete;

    const battery = entityCombobox(element, "battery_entity_id");
    expect(battery.options.map((option) => option.value)).toEqual(["sensor.robot_battery"]);
    expect((battery.querySelector('input[slot="value"]') as HTMLInputElement).value).toBe("sensor.robot_battery");
    expect(element.shadowRoot.textContent).toContain("Measure the complete dock at the wall outlet");
    expect(element.shadowRoot.querySelectorAll('select[name="additional_entity_ids"]')).toHaveLength(0);
    expect(element.shadowRoot.textContent).toContain("Additional entities (optional)");
  });

  it("explains when a vacuum has no usable same-device battery sensor", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [recorderDefinition];
    element.deviceEntities = { "*": [
      { entity_id: "vacuum.robot", name: "Robot", domain: "vacuum", device_id: "robot-device", state: "docked" },
      { entity_id: "sensor.robot_battery", name: "Robot battery", domain: "sensor", device_id: "robot-device", device_class: "battery", state: "unavailable", unit: "%" },
    ] };
    element.selectedType = "recorder";
    element.meter = { type: "dummy" };
    document.body.append(element);
    await element.updateComplete;

    for (const [name, value] of [["recorder_purpose", "complex_profile"], ["profile_recipe", "vacuum_robot"]] as const) {
      selectEntity(entityCombobox(element, name), value);
      await element.updateComplete;
    }
    selectEntity(entityCombobox(element, "vacuum_entity_id"), "vacuum.robot");
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('[role="alert"]')?.textContent).toContain("PowerCalc vacuum profiles require one");
  });

  it("submits a generic recorder entity list without hidden vacuum fields", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [recorderDefinition];
    element.deviceEntities = { "*": [{ entity_id: "climate.room", name: "Room", domain: "climate", state: "heat" }] };
    element.selectedType = "recorder";
    element.meter = { type: "dummy" };
    document.body.append(element);
    await element.updateComplete;

    selectEntity(entityCombobox(element, "recorder_purpose"), "complex_profile");
    await element.updateComplete;
    selectEntity(entityCombobox(element, "tracked_entity_ids"), "climate.room");
    const submitted = new Promise<MeasurementRequest>((resolve) => element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail)));
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    const request = await submitted;
    expect(request).toMatchObject({
      measure_type: "recorder",
      recorder_purpose: "complex_profile",
      profile_recipe: "generic",
      tracked_entity_ids: ["climate.room"],
    });
    expect(request).not.toHaveProperty("vacuum_entity_id");
    expect(request).not.toHaveProperty("battery_entity_id");
  });

  it("shows the configured power sensor as read-only measurement context", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.meter = { type: "hass", entity_id: "sensor.plug_power" };
    element.defaultMeasureDevice = "Shelly Plug S";
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="power_entity_id"]')).toBeNull();
    expect(element.shadowRoot.querySelector('input[name="measure_device"]')).toBeNull();
    expect(element.shadowRoot.querySelector(".power-meter-summary")?.textContent).toContain("Plug power · sensor.plug_power");
    expect(element.shadowRoot.querySelector(".power-meter-summary")?.textContent).toContain("Measurement device: Shelly Plug S");
    const openSettings = new Promise<void>((resolve) => element.addEventListener("open-settings", () => resolve()));
    (element.shadowRoot.querySelector(".power-meter-summary button") as HTMLButtonElement).click();
    await openSettings;
  });

  it("shows the voltage sensor the configured power meter reads alongside it", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [
      { entity_id: "sensor.plug_power", name: "Plug power", unit: "W", related_voltage_entity_id: "sensor.plug_line_voltage" },
      { entity_id: "sensor.strip_consumption", name: "Strip power", unit: "W", related_voltage_entity_id: "sensor.strip_mains" },
    ];
    element.voltages = [
      { entity_id: "sensor.plug_line_voltage", name: "Plug voltage", unit: "V", device_id: "plug-device" },
      { entity_id: "sensor.strip_mains", name: "Strip voltage", unit: "V", device_id: "strip-device" },
    ];
    element.meter = { type: "hass", entity_id: "sensor.plug_power", voltage_entity_id: "sensor.plug_line_voltage" };
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const summary = element.shadowRoot.querySelector(".power-meter-summary");
    expect(summary?.textContent).toContain("Plug power · sensor.plug_power");
    expect(summary?.textContent).toContain("Voltage: Plug voltage · sensor.plug_line_voltage");
    expect(element.shadowRoot.querySelector('select[name="voltage_entity_id"]')).toBeNull();
  });

  it("prefills the model ID from the selected measurement device", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"], device_id: "light-device", model_id: "LWA017", product_name: "Hue White Ambiance" }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", device_id: "plug-device", model_id: "WSP002" }];
    element.voltages = [];
    element.meter = { type: "hass", entity_id: "sensor.plug_power" };
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    selectEntity(entityCombobox(element, "light_entity_id"), "light.desk");
    await element.updateComplete;

    let request: MeasurementRequest | undefined;
    element.addEventListener("preflight", (event) => { request = (event as CustomEvent<MeasurementRequest>).detail; });
    element.shadowRoot.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(request).toMatchObject({ model_id: "LWA017", product_name: "Hue White Ambiance", session_name: "Desk lamp" });
  });

  it("keeps setup focused on measurement controls without repeating profile metadata guidance", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const profileSection = element.shadowRoot.querySelector(".device-section");
    expect(profileSection).toBeTruthy();
    const profileGrid = profileSection?.querySelector(".profile-grid");
    expect(profileGrid).toBeTruthy();
    // Walk the grid's direct children rather than using `:scope >` selectors, which
    // jsdom cannot resolve against a context node inside a shadow root. This keeps
    // the assertion scoped to the profile fields and excludes the nested advanced
    // timing grid, exactly as the `:scope > .grid > label` selector intended.
    const profileFields = [...(profileGrid?.children ?? [])].filter(
      (child): child is TestCombobox => child.tagName === "MEASURE-COMBOBOX",
    );
    const labels = profileFields.map((field) => field.label);
    expect(labels).toEqual(["Light"]);
    expect(element.shadowRoot.querySelector('input[name="model_id"]')).toBeNull();
    expect(element.shadowRoot.querySelector('input[name="product_name"]')).toBeNull();
    expect(profileSection?.textContent).not.toContain("model ID and product name in Prepare after the measurement");
    expect(profileSection?.textContent).toContain("What do you want to measure?");
    expect(element.shadowRoot.querySelectorAll("fieldset.section")).toHaveLength(0);
    expect(element.shadowRoot.querySelector(".setup-summary .type-chip")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".setup-summary .power-meter-summary")).toBeTruthy();
  });
});
