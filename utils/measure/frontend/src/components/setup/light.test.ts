import type { MeasureDefinition, MeasureParameter, MeasurementRequest } from "../../types";
import "./view";
import { SetupViewElement, capabilities, lightDefinition, lights } from "../testing/fixtures";
import { entityCombobox, selectEntity } from "./test-helpers";

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
