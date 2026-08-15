import type { MeasureDefinition, MeasureParameter, MeasurementRequest } from "../types";
import "./setup-view";
import { SetupViewElement, capabilities, definitions, lightDefinition, lights } from "./test-fixtures";

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

    expect(element.shadowRoot.textContent).toContain("Desk lamp · light.desk");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.querySelector("details")?.open).toBe(false);
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
    expect((element.shadowRoot.querySelector('input[name="sleep_time"]') as HTMLInputElement).value).toBe("1");
    expect((element.shadowRoot.querySelector('input[name="sleep_time_sample"]') as HTMLInputElement).disabled).toBe(false);
    expect((element.shadowRoot.querySelector('input[name="bri_bri_steps"]') as HTMLInputElement).value).toBe("1");
    // The desk lamp supports brightness only, so no other mode's parameters are offered at all.
    const unsupported = ["ct_bri_steps", "ct_mired_steps", "hs_bri_steps", "hs_hue_steps", "hs_sat_steps", "effect_bri_steps", "measure_time_effect"];
    expect(unsupported.filter((name) => element.shadowRoot.querySelector(`input[name="${name}"]`))).toEqual([]);

    const light = element.shadowRoot.querySelector('select[name="light_entity_id"]') as HTMLSelectElement;
    light.value = "light.desk";
    light.dispatchEvent(new Event("change"));
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
    (element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value = "LCT010";
    (element.shadowRoot.querySelector('input[name="product_name"]') as HTMLInputElement).value = "Test light";
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

    expect(element.shadowRoot.querySelectorAll('select[name="light_entity_id"]')).toHaveLength(2);
    const removeButton = element.shadowRoot.querySelector<HTMLButtonElement>("button.remove-entity");
    expect(removeButton?.getAttribute("aria-label")).toBe("Remove Light");
    expect(removeButton?.querySelector("svg")).toBeTruthy();
    expect(removeButton?.textContent?.trim()).toBe("");
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
    expect((element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value).toBe("LWA017");
    expect((element.shadowRoot.querySelector('input[name="multiple_light_count"]') as HTMLInputElement).value).toBe("2");

    (element.shadowRoot.querySelector('input[name="product_name"]') as HTMLInputElement).value = "Two identical lights";
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
    expect(element.shadowRoot.querySelectorAll('select[name="light_entity_id"]')).toHaveLength(1);
    expect(element.shadowRoot.querySelector(".multiple-lights")?.textContent).toContain("very low power use");

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="measure_multiple_lights"]')!.click();
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".add-entity")).not.toBeNull();
    expect(element.shadowRoot.querySelector('input[name="multiple_light_count"][type="number"]')).not.toBeNull();
    const helpLink = element.shadowRoot.querySelector<HTMLAnchorElement>(".multiple-lights .help-link");
    expect(helpLink?.href).toBe("https://docs.powercalc.nl/contributing/measure/lights/#multiple-identical-lights");
    expect(helpLink?.getAttribute("aria-label")).toBe("Learn more about measuring multiple identical lights");
    expect(helpLink?.querySelector("svg")).toBeTruthy();
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
  });

  it("submits a dummy light controller when the developer virtual-device toggle is on", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = { ...capabilities, developer_mode: true };
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    element.defaultMeasureDevice = "Shelly Plug S";
    document.body.append(element);
    await element.updateComplete;

    element.shadowRoot.querySelector<HTMLInputElement>('input[name="use_dummy_controller"]')!.click();
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('select[name="light_entity_id"]')).toBeNull();
    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toEqual(["brightness", "color_temp", "hs", "effect"]);

    const submitted = new Promise<MeasurementRequest>((resolve) => {
      element.addEventListener("preflight", (event) => resolve((event as CustomEvent<MeasurementRequest>).detail));
    });
    (element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value = "dummy";
    (element.shadowRoot.querySelector('input[name="product_name"]') as HTMLInputElement).value = "Virtual light";
    (element.shadowRoot.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    const request = await submitted;
    expect(request.measure_type).toBe("light");
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
    (element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value = "dummy";
    (element.shadowRoot.querySelector('input[name="product_name"]') as HTMLInputElement).value = "Virtual fan";
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

    const fanSelect = element.shadowRoot.querySelector('select[name="fan_entity_id"]') as HTMLSelectElement;
    expect(fanSelect).toBeTruthy();
    expect(fanSelect.textContent).toContain("Bedroom fan · fan.bedroom");
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
      expectedFields: ["fan_entity_id", "model_id", "product_name"],
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
      expectedFields: ["media_player_entity_id", "disable_streaming", "model_id", "product_name"],
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
      expectedFields: ["charging_device_type", "charging_entity_id", "model_id", "product_name"],
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

    const profileSection = [...element.shadowRoot.querySelectorAll("fieldset.section")][1];
    // Query from the profile grid directly instead of using a `:scope >` selector.
    // jsdom's selector engine does not resolve `:scope` against a context node that
    // lives inside a shadow root, so those selectors match nothing under the app's
    // shadow DOM even though browsers resolve them fine.
    const profileGrid = profileSection?.querySelector(".profile-grid");
    const fields = [...(profileGrid?.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[name]") ?? [])];
    expect(fields.map((field) => field.name)).toEqual(expectedFields);

    const entity = element.shadowRoot.querySelector(`select[name="${entityField}"]`) as HTMLSelectElement;
    entity.value = entityId;
    entity.dispatchEvent(new Event("change"));
    await element.updateComplete;

    expect((element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement).value).toBe(modelId);
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

    const entity = element.shadowRoot.querySelector('[name="charging_entity_id"]') as HTMLSelectElement;
    expect(entity.textContent).toContain("Downstairs vacuum");
    expect(entity.textContent).not.toContain("Garden mower");

    const type = element.shadowRoot.querySelector('[name="charging_device_type"]') as HTMLSelectElement;
    type.value = "lawn_mower_robot";
    type.dispatchEvent(new Event("change"));
    await element.updateComplete;

    const updated = element.shadowRoot.querySelector('[name="charging_entity_id"]') as HTMLSelectElement;
    expect(updated.textContent).toContain("Garden mower");
    expect(updated.textContent).not.toContain("Downstairs vacuum");
  });
});

describe("setup view defaults", () => {
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
    element.lights = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"], device_id: "light-device", model_id: "LWA017" }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", device_id: "plug-device", model_id: "WSP002" }];
    element.voltages = [];
    element.meter = { type: "hass", entity_id: "sensor.plug_power" };
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const light = element.shadowRoot.querySelector('select[name="light_entity_id"]') as HTMLSelectElement;
    light.value = "light.desk";
    light.dispatchEvent(new Event("change"));
    await element.updateComplete;

    const modelId = element.shadowRoot.querySelector('input[name="model_id"]') as HTMLInputElement;
    expect(modelId.value).toBe("LWA017");
  });

  it("orders the light fields by dependency and explains the full product name", async () => {
    const element = document.createElement("measure-setup-view") as SetupViewElement;
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power" }];
    element.voltages = [];
    element.definitions = [lightDefinition];
    element.selectedType = "light";
    document.body.append(element);
    await element.updateComplete;

    const profileSection = [...element.shadowRoot.querySelectorAll("fieldset.section")][1];
    expect(profileSection).toBeTruthy();
    const profileGrid = profileSection?.querySelector(".profile-grid");
    expect(profileGrid).toBeTruthy();
    // Walk the grid's direct children rather than using `:scope >` selectors, which
    // jsdom cannot resolve against a context node inside a shadow root. This keeps
    // the assertion scoped to the profile fields and excludes the nested advanced
    // timing grid, exactly as the `:scope > .grid > label` selector intended.
    const profileFields = [...(profileGrid?.children ?? [])].filter(
      (child): child is HTMLLabelElement => child.tagName === "LABEL",
    );
    const labels = profileFields.map(
      (field) => [...field.children].find((child) => child.tagName === "SPAN")?.textContent?.trim(),
    );
    expect(labels).toEqual(["Light"]);
    expect([...element.shadowRoot.querySelectorAll(".profile-fields > label > span")].map((label) => label.textContent?.trim()))
      .toEqual(["Model ID", "Full product name"]);
    expect(element.shadowRoot.querySelector(".field-hint")?.textContent).toContain("complete marketed name");
  });
});
