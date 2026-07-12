import type { AppSettings, Capabilities, EntityDescriptor, SessionSnapshot } from "../types";
import { AppShell } from "./app-shell";
import "./result-view";
import "./running-view";
import "./settings-view";
import "./setup-view";

const capabilities: Capabilities = {
  modes: ["brightness", "color_temp", "hs", "effect"],
  defaults: { sleep_time: 1, sample_count: 5, brightness_step: 5, hue_step: 10, saturation_step: 10, color_temp_step: 5 },
};

const lights: EntityDescriptor[] = [{ entity_id: "light.desk", name: "Desk lamp", supported_modes: ["brightness"] }];

describe("setup view", () => {
  it("renders dynamic entities, mode choices, and collapsed advanced settings", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      selectedLightId: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.selectedLightId = "light.desk";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Desk lamp · light.desk");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.querySelector("details")?.open).toBe(false);
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);

    const light = element.shadowRoot.querySelector('select[name="light_entity_id"]') as HTMLSelectElement;
    light.value = "light.desk";
    light.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
  });

  it("auto-selects every supported color mode for a capable light", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.rgb", name: "RGB lamp", supported_modes: ["brightness", "color_temp", "hs"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    document.body.append(element);
    await element.updateComplete;

    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toEqual(["brightness", "color_temp", "hs", "effect"]);
  });

  it("includes effect mode when the light exposes effects", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = [{ entity_id: "light.effect", name: "Effect lamp", supported_modes: ["brightness", "effect"], effect_list: ["colorloop"] }];
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    document.body.append(element);
    await element.updateComplete;

    const labels = [...element.shadowRoot.querySelectorAll("label.check")].map((label) => label.textContent?.trim());
    expect(labels).toContain("Effect");
    const checkedModes = [...element.shadowRoot.querySelectorAll<HTMLInputElement>('input[name="modes"]:checked')].map((input) => input.value);
    expect(checkedModes).toContain("effect");
  });
});

describe("running view", () => {
  it("shows progress, phase, connection state, and cancellation", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      connected: boolean;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", phase: "Brightness", mode: "brightness", progress: { completed: 25, total: 100, estimated_remaining_seconds: 120 } };
    element.connected = true;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("25%");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.textContent).toContain("Live");
    expect(element.shadowRoot.querySelector("progress")?.value).toBe(25);
    expect(element.shadowRoot.querySelector("button")?.textContent).toContain("Cancel measurement");
  });
});

describe("setup view defaults", () => {
  it("preselects the default power sensor for a new measurement", async () => {
    const element = document.createElement("measure-setup-view") as HTMLElement & {
      capabilities: Capabilities;
      lights: EntityDescriptor[];
      powers: EntityDescriptor[];
      voltages: EntityDescriptor[];
      defaultPowerEntityId: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    element.defaultPowerEntityId = "sensor.plug_power";
    document.body.append(element);
    await element.updateComplete;

    const power = element.shadowRoot.querySelector('select[name="power_entity_id"]') as HTMLSelectElement;
    expect(power.value).toBe("sensor.plug_power");
  });
});

describe("settings view", () => {
  it("lists power sensors and emits the selected default on save", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[];
      settings: AppSettings;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.settings = { default_power_entity_id: null };
    document.body.append(element);
    await element.updateComplete;

    const saved = new Promise<AppSettings>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    const select = element.shadowRoot.querySelector('select[name="default_power_entity_id"]') as HTMLSelectElement;
    select.value = "sensor.plug_power";
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await saved).default_power_entity_id).toBe("sensor.plug_power");
  });
});

describe("app shell", () => {
  it("keeps Settings in the app bar and labels each measurement step", async () => {
    vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
    const element = document.createElement("powercalc-measure-app") as AppShell;
    element.view = "running";
    element.snapshot = { state: "running" };
    document.body.append(element);
    await element.updateComplete;

    const topbar = element.shadowRoot?.querySelector(".topbar");
    const steps = [...(element.shadowRoot?.querySelectorAll(".sequence > li") ?? [])];
    expect(topbar?.querySelector(".settings-toggle")?.textContent).toContain("Settings");
    expect(steps.map((step) => step.textContent?.trim())).toEqual(["✓Set up", "✓Review", "3Measure", "4Result"]);
    expect(steps.at(2)?.getAttribute("aria-current")).toBe("step");
  });
});

describe("result view", () => {
  it("shows a download-all action for generated files", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      files: { name: string; size: number; media_type: string }[];
      fileUrl: (name: string) => string;
      downloadAll: () => void;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    const downloadAll = vi.fn();
    element.snapshot = { state: "completed" };
    element.files = [
      { name: "model.csv", size: 1234, media_type: "text/csv" },
      { name: "model.json", size: 5678, media_type: "application/json" },
    ];
    element.fileUrl = (name) => `/download/${name}`;
    element.downloadAll = downloadAll;
    document.body.append(element);
    await element.updateComplete;

    const button = element.shadowRoot.querySelector(".download-all") as HTMLButtonElement;
    expect(button.textContent).toContain("Download all");
    button.click();
    expect(downloadAll).toHaveBeenCalledTimes(1);
  });
});
