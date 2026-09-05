import type { MeasureDefinition, MeasureParameter, MeasurementRequest } from "../../types";
import "./setup-view";
import { recorderExportFilename } from "./setup-view";
import { SetupViewElement, capabilities, definitions, lightDefinition, lights } from "../testing/test-fixtures";

interface TestCombobox extends HTMLElement {
  label: string;
  value: string | string[];
  options: Array<{ value: string; label: string }>;
  updateComplete: Promise<boolean>;
  shadowRoot: ShadowRoot;
}

function entityCombobox(element: SetupViewElement, name: string): TestCombobox {
  return element.shadowRoot.querySelector(`measure-combobox[name="${name}"]`) as TestCombobox;
}

function selectEntity(picker: TestCombobox, value: string): void {
  picker.value = value;
  const input = picker.querySelector('input[slot="value"]') as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

const recorderDefinition: MeasureDefinition = {
  measure_type: "recorder",
  label: "Recorder",
  description: "Record power and entity states.",
  icon: "⏺",
  model_id_example: "",
  product_name_example: "",
  parameters: [],
  supports_profile: false,
  supports_resume: false,
  fields: [
    { name: "power_entity_id", role: "power_meter", label: "Power sensor", control: "entity", required: true, options: [] },
    {
      name: "recorder_purpose", role: "attribute", label: "What do you want to create?", control: "select", required: true,
      default: "playbook", review: true,
      options: [
        { value: "playbook", label: "A Playbook CSV", description: "Record the playbook format." },
        {
          value: "complex_profile",
          label: "Data for a complex power profile (experimental)",
          description: "This workflow is not feature complete and does not create a profile model.json yet.",
        },
      ],
    },
    {
      name: "profile_recipe", role: "attribute", label: "Device type", control: "select", required: true,
      default: "generic", visible_when: { recorder_purpose: ["complex_profile"] }, review: true,
      options: [
        { value: "generic", label: "Generic device", description: "Choose relevant entities." },
        { value: "vacuum_robot", label: "Robot vacuum", description: "Capture the vacuum and battery.", guidance: ["Measure the complete dock at the wall outlet."] },
      ],
    },
    {
      name: "tracked_entity_ids", role: "attribute", label: "Tracked entity", plural_label: "Tracked entities",
      control: "entity", required: true, multiple: true, all_entities: true,
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["generic"] }, options: [], review: true,
    },
    {
      name: "vacuum_entity_id", role: "attribute", label: "Vacuum", control: "entity", required: true,
      all_entities: true, entity_domains: ["vacuum"],
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["vacuum_robot"] }, options: [], review: true,
    },
    {
      name: "battery_entity_id", role: "attribute", label: "Battery level sensor", control: "entity", required: true,
      all_entities: true, entity_device_classes: ["battery"], related_to: "vacuum_entity_id", same_device_only: true,
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["vacuum_robot"] }, options: [],
      hint: "PowerCalc vacuum profiles require a battery sensor.", review: true,
    },
    {
      name: "additional_entity_ids", role: "attribute", label: "Additional entity", plural_label: "Additional entities (optional)",
      control: "entity", required: false, multiple: true, all_entities: true, related_to: "vacuum_entity_id",
      visible_when: { recorder_purpose: ["complex_profile"], profile_recipe: ["vacuum_robot"] }, options: [], review: true,
    },
    { name: "export_filename", role: "attribute", label: "Export filename", control: "text", required: true, default: "record.csv", options: [] },
  ],
};

describe("setup view", () => {
  it("renders dynamic entities, mode choices, and collapsed advanced settings", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.selectedEntities = { light_entity_id: ["light.desk"] };
    document.body.append(element);
    await element.updateComplete;

    const light = entityCombobox(element, "light_entity_id");
    await light.updateComplete;
    expect((light.shadowRoot.querySelector("input") as HTMLInputElement).value).toBe("Desk lamp · light.desk");
    expect(element.shadowRoot.querySelector(".discovery-help")?.textContent).toContain("If a light is missing, change its state once in Home Assistant, then reload this page.");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.querySelector("details")?.open).toBe(false);
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
    expect((element.shadowRoot.querySelector('input[name="sleep_time"]') as HTMLInputElement).value).toBe("1");
    expect((element.shadowRoot.querySelector('input[name="sleep_time_sample"]') as HTMLInputElement).disabled).toBe(false);
    expect((element.shadowRoot.querySelector('input[name="bri_bri_steps"]') as HTMLInputElement).value).toBe("1");
    // The desk lamp supports brightness only, so no other mode's parameters are offered at all.
    const unsupported = ["ct_bri_steps", "ct_mired_steps", "hs_bri_steps", "hs_hue_steps", "hs_sat_steps", "effect_bri_steps", "measure_time_effect"];
    expect(unsupported.filter((name) => element.shadowRoot.querySelector(`input[name="${name}"]`))).toEqual([]);

    selectEntity(light, "light.desk");
    await element.updateComplete;
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
  });

  it("auto-selects every supported color mode for a capable light", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.rgb", name: "RGB lamp", supported_modes: ["brightness", "color_temp", "hs"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toEqual(["brightness", "color_temp", "hs", "effect"]);
  });

  it("warns that an active light setup check controls the light and leaves it off", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.rgb", name: "RGB lamp", supported_modes: ["brightness", "hs"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("briefly controls the selected light");
    expect(element.shadowRoot.querySelector<HTMLButtonElement>('button[type="submit"]')?.textContent).toBe("Check light and setup");

    element.busy = true;
    await element.updateComplete;
    const progress = element.shadowRoot.querySelector('[role="status"]');
    expect(progress?.textContent).toContain("Checking low-load light settings");
    expect(progress?.textContent).toContain("representative low-load points");
    expect(progress?.querySelector("progress")?.hasAttribute("value")).toBe(false);

    element.busy = false;
    element.errorMessage = "The meter repeatedly returned 0 W.";
    element.errorHelp = {
      url: "https://docs.powercalc.nl/contributing/measure/low-power-measurements/",
      label: "Low-power measurement guide",
    };
    await element.updateComplete;
    const guide = element.shadowRoot.querySelector<HTMLAnchorElement>('[role="alert"] a');
    expect(guide?.textContent).toBe("Low-power measurement guide");
    expect(guide?.href).toBe("https://docs.powercalc.nl/contributing/measure/low-power-measurements/");
    expect(guide?.target).toBe("_blank");
    expect(guide?.rel).toBe("noopener noreferrer");
  });

  it("submits mode-specific native light-grid steps", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.rgb", name: "RGB lamp", supported_modes: ["brightness", "color_temp", "hs"] }];
    element.powers = [{
      entity_id: "sensor.plug_power",
      name: "Plug power",
      unit: "W",
      related_voltage_entity_id: "sensor.plug_voltage",
    }];
    element.voltages = [{ entity_id: "sensor.plug_voltage", name: "Plug voltage", unit: "V" }];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.selectedEntities = { light_entity_id: ["light.rgb"] };
    element.meter = { type: "hass", entity_id: "sensor.plug_power", voltage_entity_id: "sensor.plug_voltage" };
    element.defaultMeasureDevice = "Shelly Plug S";
    document.body.append(element);
    await element.updateComplete;

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_load"]')!.click();
    await element.updateComplete;
    element.shadowRoot.querySelector<HTMLInputElement>('input[name="dummy_load_description"]')!.value = "Incandescent reference load";
    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    const request = await submitted;
    expect(request.measure_type).toBe("light");
    expect(request.measure_device).toBe("Shelly Plug S");
    expect(request.dummy_load).toEqual({ mode: "calibrate", description: "Incandescent reference load" });
    expect(request.parameters).toMatchObject({
      bri_bri_steps: 1,
      ct_bri_steps: 5,
      ct_mired_steps: 10,
      hs_bri_steps: 32,
      hs_hue_steps: 2731,
      hs_sat_steps: 32,
    });
  });

  it("submits multiple lights, intersects their modes, and infers model and count", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [
      {
        entity_id: "light.one",
        name: "One group",
        model_id: "LWA017",
        supported_modes: ["brightness", "hs"],
        member_entity_ids: ["light.member_one", "light.member_two"],
      },
      { entity_id: "light.two", name: "Two", model_id: "LWA017", supported_modes: ["brightness"] },
      { entity_id: "light.member_one", name: "Member one", model_id: "LWA017", supported_modes: ["brightness"] },
      { entity_id: "light.member_two", name: "Member two", model_id: "LWA017", supported_modes: ["brightness"] },
    ];
    element.powers = [{ entity_id: "sensor.power", name: "Power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.selectedEntities = { light_entity_id: ["light.one", "light.two"] };
    element.multipleLights = true;
    element.meter = { type: "hass", entity_id: "sensor.power" };
    element.defaultMeasureDevice = "Meter";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelectorAll('measure-combobox[name="light_entity_id"]')).toHaveLength(1);
    const picker = entityCombobox(element, "light_entity_id");
    await picker.updateComplete;
    expect(picker.hasAttribute("multiple")).toBe(true);
    expect(picker.shadowRoot.querySelectorAll(".tag")).toHaveLength(2);
    expect(element.shadowRoot.querySelector("button.remove-entity")).toBeNull();
    expect(element.shadowRoot.querySelector(".discovery-help")?.textContent)
      .toContain("If a light is missing, change its state once in Home Assistant, then reload this page.");
    expect(element.shadowRoot.querySelector<HTMLDetailsElement>(".discovery-help")?.open).toBe(false);
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
    expect(element.shadowRoot.querySelector('input[name="model_id"]')).toBeNull();
    expect((element.shadowRoot.querySelector('input[name="multiple_light_count"]') as HTMLInputElement).value).toBe("2");

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );

    const request = await submitted;
    const lightRequest = request as Extract<MeasurementRequest, { measure_type: "light" }>;
    expect(lightRequest.controller).toEqual({ type: "hass_multi", entity_ids: ["light.one", "light.two"] });
    expect(lightRequest.multiple_light_count).toBe(2);
    expect(lightRequest.model_id).toBe("LWA017");
  });

  it("keeps multi-light controls hidden until the user opts in", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.power", name: "Power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".add-entity")).toBeNull();
    expect(element.shadowRoot.querySelector('input[name="multiple_light_count"][type="number"]')).toBeNull();
    expect(element.shadowRoot.querySelectorAll('measure-combobox[name="light_entity_id"]')).toHaveLength(1);
    const help = element.shadowRoot.querySelector<HTMLDetailsElement>(".multiple-lights details")!;
    expect(help.open).toBe(false);
    const toggle = element.shadowRoot.querySelector<HTMLInputElement>('input[name="measure_multiple_lights"]')!;
    const grid = element.shadowRoot.querySelector(".profile-grid")!;
    expect(toggle.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="measure_multiple_lights"]')!.click();
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".multiple-lights")?.textContent).toContain("very low power use");
    expect(element.shadowRoot.querySelector(".multiple-lights")?.textContent).toContain("Select up to three individual lights");
    const groupGuide = element.shadowRoot.querySelector<HTMLAnchorElement>(
      '.multiple-lights a[href="https://www.home-assistant.io/integrations/group/"]',
    );
    expect(groupGuide?.textContent).toBe("Home Assistant light group");
    expect(groupGuide?.getAttribute("target")).toBe("_blank");
    expect(groupGuide?.getAttribute("rel")).toBe("noopener noreferrer");

    expect(element.shadowRoot.querySelector(".add-entity")).toBeNull();
    expect(entityCombobox(element, "light_entity_id").hasAttribute("multiple")).toBe(true);
    expect(element.shadowRoot.querySelector('input[name="multiple_light_count"][type="number"]')).not.toBeNull();
    const helpLink = element.shadowRoot.querySelector<HTMLAnchorElement>(".multiple-lights .help-link");
    expect(helpLink?.href).toBe("https://docs.powercalc.nl/contributing/measure/lights/#multiple-identical-lights");
    expect(helpLink?.getAttribute("aria-label")).toBe("Learn more about measuring multiple identical lights");
    expect(help.open).toBe(false);
    help.open = true;
    help.querySelector("summary")!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(help.open).toBe(false);
    help.open = true;
    help.dispatchEvent(new FocusEvent("focusout", { relatedTarget: helpLink }));
    expect(help.open).toBe(true);
    help.dispatchEvent(new FocusEvent("focusout", { relatedTarget: toggle }));
    expect(help.open).toBe(false);
    const count = element.shadowRoot.querySelector('input[name="multiple_light_count"][type="number"]')!;
    expect(count.closest(".field-with-help")?.querySelector("details")?.textContent).toContain("power per light");
    expect(count.closest("label")?.querySelector(".field-hint")).toBeNull();

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="measure_multiple_lights"]')!.click();
    await element.updateComplete;
    expect(help.open).toBe(false);
    expect(element.shadowRoot.querySelector(".add-entity")).toBeNull();
  });

  it("removes light tags, preserves a group count override, and keeps the first light when switching back", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.lights = [
      { entity_id: "light.one", name: "One", supported_modes: ["brightness", "hs"] },
      { entity_id: "light.two", name: "Two", supported_modes: ["brightness"] },
    ];
    element.multipleLights = true;
    element.selectedEntities = { light_entity_id: ["light.one", "light.two"] };
    document.body.append(element);
    await element.updateComplete;
    const picker = entityCombobox(element, "light_entity_id");
    await picker.updateComplete;
    const count = element.shadowRoot.querySelector<HTMLInputElement>('[name="multiple_light_count"]')!;
    count.value = "6";
    count.dispatchEvent(new Event("input", { bubbles: true }));

    picker.shadowRoot.querySelector<HTMLButtonElement>('[aria-label="Remove Two · light.two"]')!.click();
    await element.updateComplete;
    await picker.updateComplete;
    expect(element.selectedEntities.light_entity_id).toEqual(["light.one"]);
    expect(picker.shadowRoot.querySelectorAll(".tag")).toHaveLength(1);
    expect(count.value).toBe("6");
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(2);

    element.shadowRoot.querySelector<HTMLInputElement>('[name="measure_multiple_lights"]')!.click();
    await element.updateComplete;
    const single = entityCombobox(element, "light_entity_id");
    expect(single.hasAttribute("multiple")).toBe(false);
    expect(single.value).toBe("light.one");
    expect(element.shadowRoot.querySelector<HTMLInputElement>('[name="multiple_light_count"]')!.value).toBe("1");
  });

  it("hides the virtual-device toggle unless developer mode is enabled", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('input[name="use_dummy_controller"]')).toBeNull();
    expect(element.shadowRoot.querySelector(".developer-options")).toBeNull();
  });

  it("submits a dummy light controller when the developer virtual-device toggle is on", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = { ...capabilities, developer_mode: true, fast_test_mode: true };
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.defaultMeasureDevice = "Shelly Plug S";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector<HTMLDetailsElement>(".developer-options")?.open).toBe(false);
    expect(element.shadowRoot.querySelector(".developer-options")?.textContent).toContain("Fast test mode is enabled.");
    expect(element.shadowRoot.querySelector(".test-mode-status")).toBeNull();
    element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_controller"]')!.click();
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".test-mode-status")?.textContent).toContain("Virtual device · test output only");
    expect(element.shadowRoot.querySelector('select[name="light_entity_id"]')).toBeNull();
    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toEqual(["brightness", "color_temp", "hs", "effect"]);

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector('input[name="session_name"]') as HTMLInputElement).value = "Virtual light";
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    const request = await submitted;
    expect(request.measure_type).toBe("light");
    expect(request).toMatchObject({ model_id: "", product_name: "", session_name: "Virtual light" });
    expect("controller" in request && request.controller).toEqual({ type: "dummy" });
  });

  it("submits a dummy fan controller when the developer virtual-device toggle is on", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan",
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }] satisfies MeasureParameter[], label: "Fan", description: "Measure fan power.",
      fields: [{ name: "fan_entity_id", role: "controller", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      supports_profile: true, supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [fanDefinition];
    element.capabilities = { ...capabilities, developer_mode: true };
    element.meter = { type: "dummy" };
    element.deviceEntities = {};
    element.selectedType = "fan";
    document.body.append(element);
    await element.updateComplete;

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_controller"]')!.click();
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="fan_entity_id"]')).toBeNull();

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector('input[name="session_name"]') as HTMLInputElement).value = "Virtual fan";
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    const request = await submitted;
    expect(request.measure_type).toBe("fan");
    expect("controller" in request && request.controller).toEqual({ type: "dummy" });
  });

  it("includes effect mode when the light exposes effects", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.effect", name: "Effect lamp", supported_modes: ["brightness", "effect"], effect_list: ["colorloop"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const labels = [...element.shadowRoot.querySelectorAll("label.check")].map((label) => label.textContent?.trim());
    expect(labels).toContain("Effect");
    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toContain("effect");
    const parameter = (name: string) => element.shadowRoot.querySelector<HTMLInputElement>(`input[name="${name}"]`);
    expect(parameter("effect_bri_steps")).toBeTruthy();
    expect(parameter("measure_time_effect")).toBeTruthy();

    const effect = element.shadowRoot.querySelector<HTMLInputElement>('input[name="modes"][value="effect"]');
    if (!effect) throw new Error("Expected effect mode input");
    effect.checked = false;
    effect.dispatchEvent(new Event("change"));
    // Deselecting a mode re-renders from state rather than mutating the DOM in place.
    await element.updateComplete;
    // Every mode's parameters disappear with it, so none of them can be submitted by accident.
    expect(parameter("effect_bri_steps")).toBeNull();
    expect(parameter("measure_time_effect")).toBeNull();
    expect(parameter("bri_bri_steps")).toBeTruthy();
  });
});

describe("setup type picker", () => {
  it("uses a matching saved dummy-load calibration by default", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.powers = [{
      entity_id: "sensor.plug_power",
      name: "Plug power",
      unit: "W",
      related_voltage_entity_id: "sensor.plug_voltage",
    }];
    element.meter = { type: "hass", entity_id: "sensor.plug_power", voltage_entity_id: "sensor.plug_voltage" };
    element.defaultMeasureDevice = "Shelly Plug S";
    element.selectedType = "average";
    element.dummyLoadCalibration = {
      description: "60 W incandescent bulb",
      resistance: 882.4,
      calibrated_at: "2026-07-16T10:00:00Z",
    };
    document.body.append(element);
    await element.updateComplete;

    const enabled = element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_load"]');
    expect(enabled).toBeTruthy();
    enabled!.click();
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("60 W incandescent bulb");
    expect(element.shadowRoot.textContent).toContain("882.4 Ω");
    expect(element.shadowRoot.textContent).toContain("Use saved calibration");
    expect(element.shadowRoot.textContent).toContain("Recalibrate");

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await submitted).dummy_load).toEqual({
      mode: "reuse",
      description: "60 W incandescent bulb",
      resistance: 882.4,
    });
  });

  it("collects a load description when inline calibration is required", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.meter = { type: "shelly", device_ip: "" };
    element.selectedType = "average";
    element.dummyLoadCalibration = null;
    document.body.append(element);
    await element.updateComplete;

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_load"]')!.click();
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("at least 10 minutes");
    const description = element.shadowRoot.querySelector<HTMLInputElement>('input[name="dummy_load_description"]');
    expect(description?.required).toBe(true);
    description!.value = "Ceramic heater";

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await submitted).dummy_load).toEqual({ mode: "calibrate", description: "Ceramic heater" });
  });

  it("does not offer a resistive dummy load for the synthetic test meter", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.meter = { type: "dummy" };
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('input[name="use_dummy_load"]')).toBeNull();
    expect(element.shadowRoot.textContent).toContain("Synthetic test meter");
  });

  it("disables a resistive dummy load when the Home Assistant meter has no voltage sensor", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.meter = { type: "hass", entity_id: "sensor.plug_power" };
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_load"]')?.disabled).toBe(true);
    expect(element.shadowRoot.textContent).toContain("requires a voltage sensor");
  });

  it("requires power meter setup before choosing a measurement type", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.powerMeterConfigured = false;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Set up your power meter");
    expect(element.shadowRoot.querySelector(".type-card")).toBeNull();
    const openSettings = new Promise<void>((resolve) => element.addEventListener("open-settings", () => resolve()));
    (element.shadowRoot.querySelector(".power-meter-required button") as HTMLButtonElement).click();
    await openSettings;
  });

  it("shows a card per measurement type before a type is chosen", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelectorAll(".type-card")).toHaveLength(2);
    expect(element.shadowRoot.textContent).toContain("Measure average power for a fixed duration.");
    expect(element.shadowRoot.querySelector("form")).toBeNull();
  });

  it("renders generic fields, dedupes the power sensor, and emits one typed preflight request", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.meter = { type: "hass", entity_id: "sensor.plug_power" };
    element.defaultMeasureDevice = "Shelly Plug S";
    element.capabilities = capabilities;
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="power_entity_id"]')).toBeNull();
    expect(element.shadowRoot.querySelector(".power-meter-summary")?.textContent).toContain("Plug power · sensor.plug_power");
    expect(element.shadowRoot.querySelector(".power-meter-summary button")?.textContent).toContain("Change");
    expect(element.shadowRoot.querySelector('input[name="duration"]')).toBeTruthy();
    const readingInterval = element.shadowRoot.querySelector('input[name="sleep_time"]') as HTMLInputElement;
    expect(readingInterval).toBeTruthy();
    expect(element.shadowRoot.querySelector('input[name="sample_count"]')).toBeNull();
    readingInterval.value = "2.5";
    // The powermeter field from the definition must not be rendered a second time.
    expect(element.shadowRoot.querySelectorAll('[name="powermeter_entity_id"]')).toHaveLength(0);

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();
    const request = await submitted;
    expect(request.measure_type).toBe("average");
    expect(request.measure_device).toBe("Shelly Plug S");
    expect(request.power_meter).toEqual({ type: "hass", entity_id: "sensor.plug_power" });
    expect(request.measure_type === "average" && request.duration).toBe(60);
    expect(request.parameters.sleep_time).toBe(2.5);
    expect(request.parameters.sample_count).toBe(capabilities.defaults.sample_count);
  });

  it("includes the configured Shelly adapter in the submitted request", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.meter = { type: "shelly", device_ip: "192.0.2.20" };
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await submitted).power_meter).toEqual({ type: "shelly", device_ip: "192.0.2.20" });
  });

  it("includes the configured Kasa adapter in the submitted request", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = definitions;
    element.capabilities = capabilities;
    element.meter = { type: "kasa", device_ip: "192.0.2.30" };
    element.selectedType = "average";
    document.body.append(element);
    await element.updateComplete;

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await submitted).power_meter).toEqual({ type: "kasa", device_ip: "192.0.2.30" });
  });

  it("renders an entity dropdown for a device domain when entities are available", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan",
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }] satisfies MeasureParameter[],
      label: "Fan",
      description: "Measure fan power across percentage levels.",
      fields: [
        { name: "power_entity_id", role: "power_meter", label: "Power sensor", control: "entity", required: true, options: [] },
        { name: "fan_entity_id", role: "controller", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] },
      ],
      supports_profile: true,
      supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [fanDefinition];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.meter = { type: "hass", entity_id: "" };
    element.deviceEntities = { fan: [{ entity_id: "fan.bedroom", name: "Bedroom fan" }] };
    element.capabilities = capabilities;
    element.selectedType = "fan";
    document.body.append(element);
    await element.updateComplete;

    const fanSelect = entityCombobox(element, "fan_entity_id");
    expect(fanSelect).toBeTruthy();
    expect(fanSelect.options.map((option) => option.label)).toContain("Bedroom fan · fan.bedroom");
  });

  it.each([
    {
      type: "fan" as const,
      definition: {
        measure_type: "fan" as const,
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }] satisfies MeasureParameter[],
        label: "Fan",
        description: "Measure fan power across percentage levels.",
        fields: [
          { name: "fan_entity_id", role: "controller" as const, label: "Fan", control: "entity" as const, required: true, entity_domains: ["fan"], options: [] },
        ],
        supports_profile: true,
        supports_resume: false,
      },
      entities: { fan: [{ entity_id: "fan.bedroom", name: "Bedroom fan", model_id: "FAN-001" }] },
      entityField: "fan_entity_id",
      entityId: "fan.bedroom",
      expectedFields: ["fan_entity_id"],
      modelId: "FAN-001",
    },
    {
      type: "speaker" as const,
      definition: {
        measure_type: "speaker" as const,
        icon: "🔊",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }] satisfies MeasureParameter[],
        label: "Speaker",
        description: "Measure power across media-player volume levels.",
        fields: [
          { name: "media_player_entity_id", role: "controller" as const, label: "Media player", control: "entity" as const, required: true, entity_domains: ["media_player"], options: [] },
          { name: "disable_streaming", role: "attribute" as const, label: "Disable automatic pink-noise streaming", control: "boolean" as const, required: false, default: false, options: [] },
        ],
        supports_profile: true,
        supports_resume: false,
      },
      entities: { media_player: [{ entity_id: "media_player.office", name: "Office speaker", model_id: "SPEAKER-001" }] },
      entityField: "media_player_entity_id",
      entityId: "media_player.office",
      expectedFields: ["media_player_entity_id", "disable_streaming"],
      modelId: "SPEAKER-001",
    },
    {
      type: "charging" as const,
      definition: {
        measure_type: "charging" as const,
        icon: "🔋",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }, { name: "sample_count", label: "Samples per reading", hint: "More samples reduce noise but increase measurement time.", group: "Sampling" }, { name: "sleep_time_sample", label: "Time between samples (seconds)", hint: "Only used when taking more than one sample.", group: "Sampling", requires_multiple: "sample_count" }] satisfies MeasureParameter[],
        label: "Charging device",
        description: "Measure charging power against battery level.",
        fields: [
          {
            name: "charging_device_type",
            role: "attribute" as const,
            label: "Charging device type",
            control: "select" as const,
            required: true,
            options: [
              { value: "vacuum_robot", label: "Vacuum robot", entity_domain: "vacuum" },
              { value: "lawn_mower_robot", label: "Lawn mower robot", entity_domain: "lawn_mower" },
            ],
          },
          {
            name: "charging_entity_id",
            role: "controller" as const,
            narrowed_by: "charging_device_type",
            label: "Charging device",
            control: "entity" as const,
            required: true,
            entity_domains: ["vacuum", "lawn_mower"],
            options: [],
          },
        ],
        supports_profile: true,
        supports_resume: false,
      },
      entities: { vacuum: [{ entity_id: "vacuum.downstairs", name: "Downstairs vacuum", model_id: "VAC-001" }] },
      entityField: "charging_entity_id",
      entityId: "vacuum.downstairs",
      expectedFields: ["charging_device_type", "charging_entity_id"],
      modelId: "VAC-001",
    },
  ])("orders $type fields by dependency and prefills the selected device model ID", async ({
    type, definition, entities, entityField, entityId, expectedFields, modelId,
  }) => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [definition];
    element.capabilities = capabilities;
    element.meter = { type: "dummy" };
    element.deviceEntities = Object.fromEntries(Object.entries(entities));
    element.selectedType = type;
    document.body.append(element);
    await element.updateComplete;

    const profileSection = element.shadowRoot.querySelector(".device-section");
    // Query from the profile grid directly instead of using a `:scope >` selector.
    // jsdom's selector engine does not resolve `:scope` against a context node that
    // lives inside a shadow root, so those selectors match nothing under the app's
    // shadow DOM even though browsers resolve them fine.
    const profileGrid = profileSection?.querySelector(".profile-grid");
    const fields = [...(profileGrid?.querySelectorAll<HTMLInputElement & { name: string }>("[name]") ?? [])]
      .filter((field) => field.getAttribute("slot") !== "value");
    expect(fields.map((field) => field.name)).toEqual(expectedFields);

    selectEntity(entityCombobox(element, entityField), entityId);
    await element.updateComplete;

    let request: MeasurementRequest | undefined;
    element.addEventListener("preflight", (event) => { request = (event as CustomEvent<MeasurementRequest>).detail; });
    element.shadowRoot.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true }));
    expect(request?.model_id).toBe(modelId);
    expect(element.shadowRoot.querySelector('input[name="model_id"]')).toBeNull();
  });

  it("shows entity discovery failures instead of silently enabling free-text input", async () => {
    const fanDefinition: MeasureDefinition = {
      measure_type: "fan",
        icon: "🌀",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }] satisfies MeasureParameter[], label: "Fan", description: "Measure fan power.",
      fields: [{ name: "fan_entity_id", role: "controller", label: "Fan", control: "entity", required: true, entity_domains: ["fan"], options: [] }],
      supports_profile: false, supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [fanDefinition];
    element.capabilities = capabilities;
    element.meter = { type: "dummy" };
    element.deviceEntityErrors = { fan: "Home Assistant is unavailable" };
    element.selectedType = "fan";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".notice.error")?.textContent).toContain("Home Assistant is unavailable");
    expect(element.shadowRoot.querySelector('[name="fan_entity_id"]')).toBeNull();
  });

  it("filters charging entities by the selected device type", async () => {
    const chargingDefinition: MeasureDefinition = {
      measure_type: "charging",
        icon: "🔋",
        model_id_example: "WSP002",
        product_name_example: "",
        parameters: [{ name: "sleep_time", label: "Reading interval (seconds)", hint: "Delay between repeated power readings and retries.", step: "0.1", group: "Sampling" }, { name: "sample_count", label: "Samples per reading", hint: "More samples reduce noise but increase measurement time.", group: "Sampling" }, { name: "sleep_time_sample", label: "Time between samples (seconds)", hint: "Only used when taking more than one sample.", group: "Sampling", requires_multiple: "sample_count" }] satisfies MeasureParameter[], label: "Charging device", description: "Measure charging power.",
      fields: [
        {
          name: "charging_device_type", role: "attribute", label: "Device type", control: "select", required: true,
          options: [
            { value: "vacuum_robot", label: "Vacuum", entity_domain: "vacuum" },
            { value: "lawn_mower_robot", label: "Lawn mower", entity_domain: "lawn_mower" },
          ],
        },
        {
          name: "charging_entity_id", role: "controller", narrowed_by: "charging_device_type", label: "Charging device", control: "entity", required: true,
          entity_domains: ["vacuum", "lawn_mower"], options: [],
        },
      ],
      supports_profile: false, supports_resume: false,
    };
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.definitions = [chargingDefinition];
    element.capabilities = capabilities;
    element.meter = { type: "dummy" };
    element.deviceEntities = {
      vacuum: [{ entity_id: "vacuum.downstairs", name: "Downstairs vacuum" }],
      lawn_mower: [{ entity_id: "lawn_mower.garden", name: "Garden mower" }],
    };
    element.selectedType = "charging";
    document.body.append(element);
    await element.updateComplete;

    const entity = entityCombobox(element, "charging_entity_id");
    expect(entity.options.map((option) => option.label)).toContain("Downstairs vacuum · vacuum.downstairs");
    expect(entity.options.map((option) => option.label)).not.toContain("Garden mower · lawn_mower.garden");

    selectEntity(entityCombobox(element, "charging_device_type"), "lawn_mower_robot");
    await element.updateComplete;

    const updated = entityCombobox(element, "charging_entity_id");
    expect(updated.options.map((option) => option.label)).toContain("Garden mower · lawn_mower.garden");
    expect(updated.options.map((option) => option.label)).not.toContain("Downstairs vacuum · vacuum.downstairs");
  });
});

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

describe("recorderExportFilename", () => {
  it("follows the recorder purpose rather than the name a duplicated session left behind", () => {
    expect(recorderExportFilename("complex_profile", "kitchen.csv")).toBe("kitchen.jsonl");
    expect(recorderExportFilename("playbook", "kitchen.jsonl")).toBe("kitchen.csv");
  });

  it("shows the name the server will actually write for the default", () => {
    expect(recorderExportFilename("complex_profile", "record.csv")).toBe("record.jsonl");
    expect(recorderExportFilename("playbook", "record.csv")).toBe("record.csv");
    expect(recorderExportFilename("complex_profile", "")).toBe("record.jsonl");
  });

  it("leaves an extension it does not manage alone", () => {
    expect(recorderExportFilename("complex_profile", "kitchen.txt")).toBe("kitchen.txt");
    expect(recorderExportFilename("playbook", "kitchen")).toBe("kitchen");
  });
});
