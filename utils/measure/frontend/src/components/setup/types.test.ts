import type { MeasureDefinition, MeasureParameter, MeasurementRequest } from "../../types";
import "./view";
import { SetupViewElement, capabilities, definitions } from "../testing/fixtures";
import { entityCombobox, selectEntity } from "./test-helpers";

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
