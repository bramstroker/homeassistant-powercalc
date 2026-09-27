import type { MeasurementRequest } from "../../types";
import "./view";
import { SetupViewElement, capabilities, lightDefinition, lights } from "../testing/fixtures";
import type { TestCombobox } from "./test-helpers";
import { entityCombobox, recorderDefinition, selectEntity } from "./test-helpers";

describe("setup view defaults", () => {
  it.each([{ selection: [] }, { selection: ["sensor.manual"] }])("preserves saved vacuum selections $selection when suggestions exist", async ({ selection }) => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [recorderDefinition];
    element.deviceEntities = { "*": [
      { entity_id: "vacuum.robot", name: "Robot", domain: "vacuum", device_id: "robot",
        suggested_recording_entity_ids: ["sensor.status"] },
      { entity_id: "sensor.battery", name: "Battery", domain: "sensor", device_id: "robot", device_class: "battery", unit: "%", state: "42" },
      { entity_id: "sensor.status", name: "Status", domain: "sensor", device_id: "robot" },
      { entity_id: "sensor.manual", name: "Manual", domain: "sensor", device_id: "robot" },
    ] };
    element.selectedType = "recorder";
    element.initialRequest = {
      measure_type: "recorder", controller: null, model_id: "", product_name: "", measure_device: "",
      power_meter: { type: "dummy" }, generate_model: false, parameters: capabilities.defaults, resume_policy: "new",
      recorder_purpose: "complex_profile", profile_recipe: "vacuum_robot", vacuum_entity_id: "vacuum.robot",
      battery_entity_id: "sensor.battery", additional_entity_ids: selection,
    };
    element.meter = { type: "dummy" };
    document.body.append(element);
    await element.updateComplete;
    expect(entityCombobox(element, "additional_entity_ids").value).toEqual(selection);
  });

  it.each([true, false])("restores primary and secondary signals from a saved generic request (legacy=%s)", async (legacy) => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [recorderDefinition];
    element.deviceEntities = {
      "*": [
        { entity_id: "climate.room", name: "Room", domain: "climate", state: "heat", device_id: "room" },
        { entity_id: "sensor.room", name: "Room state", domain: "sensor", state: "heat", device_id: "room" },
        { entity_id: "sensor.mode", name: "Mode", domain: "sensor", state: "eco", device_id: "room" },
      ],
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
      ...(legacy
        ? { tracked_entity_ids: ["sensor.room", "sensor.mode"] }
        : { primary_entity_id: "climate.room", profile_device_type: "heating", tracked_entity_ids: ["sensor.mode"] }),
    };
    element.meter = { type: "dummy" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('[name="recorder_purpose"]')).toBeTruthy();
    expect(element.shadowRoot.querySelector('[name="profile_recipe"]')).toBeTruthy();
    const trackedEntity = entityCombobox(element, "primary_entity_id");
    expect(trackedEntity).toBeTruthy();
    expect((trackedEntity.querySelector('input[slot="value"]') as HTMLInputElement).value).toBe(legacy ? "sensor.room" : "climate.room");
    expect(entityCombobox(element, "profile_device_type").value).toBe(legacy ? "generic_iot" : "heating");
    const additional = entityCombobox(element, "tracked_entity_ids");
    expect(additional.value).toEqual(["sensor.mode"]);
    expect(additional.options.map((option) => option.value)).not.toContain(legacy ? "sensor.room" : "climate.room");
    expect(element.shadowRoot.textContent).toContain("states may explain power changes");
    additional.dispatchEvent(new CustomEvent("combobox-change", { detail: { value: [] } }));
    await element.updateComplete;
    expect(entityCombobox(element, "tracked_entity_ids").value).toEqual([]);
    selectEntity(entityCombobox(element, "primary_entity_id"), "");
    await element.updateComplete;
    expect(entityCombobox(element, "primary_entity_id").value).toBe("");
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
    expect(element.shadowRoot.querySelector('[name="model_id"]')).toBeNull();
    expect(element.shadowRoot.textContent).toContain("Record the playbook format");

    const requestedDomains = new Promise<string[]>((resolve) => {
      element.addEventListener("entity-domains-requested", (event) => resolve((event as CustomEvent<string[]>).detail));
    });
    selectEntity(entityCombobox(element, "recorder_purpose"), "complex_profile");
    await element.updateComplete;

    expect(await requestedDomains).toContain("*");
    expect(element.shadowRoot.querySelector('[name="profile_recipe"]')).toBeTruthy();
    expect(element.shadowRoot.querySelector('[name="primary_entity_id"]')).toBeTruthy();
    expect(element.shadowRoot.querySelector('[name="model_id"]')).toBeNull();
    expect(element.shadowRoot.querySelector('[name="product_name"]')).toBeNull();
    expect(element.shadowRoot.textContent).toContain("experimental workflow");
    expect(element.shadowRoot.textContent).toContain("composites from a secondary signal");
    expect(element.shadowRoot.querySelector('[name="export_filename"]')).toBeNull();
  });

  it("prefills the battery and suggested signals, preserves edits, and resets for another vacuum", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [recorderDefinition];
    element.deviceEntities = { "*": [
      { entity_id: "vacuum.robot", name: "Robot", domain: "vacuum", device_id: "robot-device", state: "docked",
        suggested_recording_entity_ids: ["sensor.dock_state", "switch.dock_drying"],
        disabled_recording_entity_ids: ["switch.dock_washing"] },
      { entity_id: "switch.dock_drying", name: "Drying", domain: "switch", device_id: "dock-device", state: "off" },
      { entity_id: "sensor.robot_battery", name: "Robot battery", domain: "sensor", device_id: "robot-device", device_class: "battery", state: "42", unit: "%" },
      { entity_id: "sensor.other_battery", name: "Other battery", domain: "sensor", device_id: "other-device", device_class: "battery", state: "80", unit: "%" },
      { entity_id: "sensor.dock_state", name: "Dock state", domain: "sensor", device_id: "robot-device", state: "idle" },
      ...Array.from({ length: 160 }, (_, index) => ({
        entity_id: `sensor.robot_${index}`, name: `Robot ${index}`, domain: "sensor", device_id: "robot-device", state: "idle",
      })),
      { entity_id: "vacuum.other", name: "Other robot", domain: "vacuum", device_id: "other-device", state: "docked" },
      { entity_id: "sensor.other_state", name: "Other state", domain: "sensor", device_id: "other-device", state: "idle" },
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
    const additional = entityCombobox(element, "additional_entity_ids");
    expect(additional.label).toBe("Additional entities (optional)");
    expect(additional.options.map((option) => option.value)).not.toContain("vacuum.robot");
    expect(additional.options.map((option) => option.value)).not.toContain("sensor.robot_battery");
    expect(additional.value).toEqual(["sensor.dock_state", "switch.dock_drying"]);
    expect(element.shadowRoot.textContent).toContain("Useful activity entities are disabled: switch.dock_washing");
    expect(element.shadowRoot.textContent).toContain("Known activity entities are selected automatically");
    const submitted = new Promise<MeasurementRequest>((resolve) => element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail)));
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(await submitted).toMatchObject({
      vacuum_entity_id: "vacuum.robot", battery_entity_id: "sensor.robot_battery",
      additional_entity_ids: ["sensor.dock_state", "switch.dock_drying"],
    });

    additional.dispatchEvent(new CustomEvent("combobox-change", { detail: { value: ["sensor.dock_state"] } }));
    await element.updateComplete;
    expect(entityCombobox(element, "additional_entity_ids").value).toEqual(["sensor.dock_state"]);

    additional.dispatchEvent(new CustomEvent("combobox-change", { detail: { value: [] } }));
    await element.updateComplete;
    element.deviceEntities = { ...element.deviceEntities };
    await element.updateComplete;
    expect(entityCombobox(element, "additional_entity_ids").value).toEqual([]);

    selectEntity(entityCombobox(element, "vacuum_entity_id"), "vacuum.other");
    await element.updateComplete;
    expect(entityCombobox(element, "additional_entity_ids").value).toEqual([]);
    expect(entityCombobox(element, "battery_entity_id").value).toBe("sensor.other_battery");
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
    expect(element.shadowRoot.querySelector('[role="alert"]')).toBeNull();
    selectEntity(entityCombobox(element, "vacuum_entity_id"), "vacuum.robot");
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('[role="alert"]')?.textContent).toContain("PowerCalc vacuum profiles require one");

    selectEntity(entityCombobox(element, "vacuum_entity_id"), "");
    await element.updateComplete;
    expect(element.shadowRoot.querySelector('[role="alert"]')).toBeNull();
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
    selectEntity(entityCombobox(element, "profile_device_type"), "heating");
    await element.updateComplete;
    selectEntity(entityCombobox(element, "primary_entity_id"), "climate.room");
    await element.updateComplete;
    const submitted = new Promise<MeasurementRequest>((resolve) => element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail)));
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    const request = await submitted;
    expect(request).toMatchObject({
      measure_type: "recorder",
      generate_model: true,
      model_id: "",
      product_name: "",
      recorder_purpose: "complex_profile",
      profile_recipe: "generic",
      primary_entity_id: "climate.room",
      profile_device_type: "heating",
      tracked_entity_ids: [],
    });
    expect(request).not.toHaveProperty("vacuum_entity_id");
    expect(request).not.toHaveProperty("battery_entity_id");
  });

  it("narrows the primary entity to the selected profile device type", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [recorderDefinition];
    element.deviceEntities = { "*": [
      { entity_id: "camera.porch", name: "Porch", domain: "camera", state: "idle", device_id: "porch",
        related_device_ids: ["porch-child", "porch-parent"] },
      { entity_id: "sensor.mode", name: "Mode", domain: "sensor", state: "day", device_id: "porch" },
      { entity_id: "sensor.child", name: "Child", domain: "sensor", state: "on", device_id: "porch-child" },
      { entity_id: "sensor.parent", name: "Parent", domain: "sensor", state: "on", device_id: "porch-parent" },
      { entity_id: "sensor.other", name: "Other", domain: "sensor", state: "on", device_id: "unrelated" },
      { entity_id: "switch.plug", name: "Plug", domain: "switch", state: "on" },
      { entity_id: "light.plug", name: "Plug light", domain: "light", state: "on" },
    ] };
    element.selectedType = "recorder";
    element.meter = { type: "dummy" };
    document.body.append(element);
    await element.updateComplete;

    selectEntity(entityCombobox(element, "recorder_purpose"), "complex_profile");
    await element.updateComplete;
    selectEntity(entityCombobox(element, "profile_device_type"), "camera");
    await element.updateComplete;
    expect(entityCombobox(element, "primary_entity_id").options.map((option) => option.value)).toEqual(["camera.porch"]);
    selectEntity(entityCombobox(element, "primary_entity_id"), "camera.porch");
    await element.updateComplete;
    expect(entityCombobox(element, "tracked_entity_ids").options.map((option) => option.value)).toEqual([
      "sensor.mode", "sensor.child", "sensor.parent",
    ]);

    selectEntity(entityCombobox(element, "profile_device_type"), "smart_switch");
    await element.updateComplete;
    expect(entityCombobox(element, "primary_entity_id").options.map((option) => option.value)).toEqual([
      "switch.plug", "light.plug",
    ]);
    expect(entityCombobox(element, "primary_entity_id").value).toBe("");
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
    document.body.append(element);
    await element.updateComplete;
    (element.shadowRoot.querySelector(".device-card") as HTMLButtonElement).click();
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
    document.body.append(element);
    await element.updateComplete;
    (element.shadowRoot.querySelector(".device-card") as HTMLButtonElement).click();
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
