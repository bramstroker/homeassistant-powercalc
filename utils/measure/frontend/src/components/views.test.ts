import type { Capabilities, EntityDescriptor, SessionSnapshot } from "../types";
import "./running-view";
import "./setup-view";

const capabilities: Capabilities = {
  modes: ["brightness", "color_temp", "hs"],
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
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.capabilities = capabilities;
    element.lights = lights;
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.voltages = [];
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Desk lamp · light.desk");
    expect(element.shadowRoot.textContent).toContain("Hue & saturation");
    expect(element.shadowRoot.querySelector("details")?.open).toBe(false);
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(3);

    const light = element.shadowRoot.querySelector('select[name="light_entity_id"]') as HTMLSelectElement;
    light.value = "light.desk";
    light.dispatchEvent(new Event("change"));
    await element.updateComplete;
    expect(element.shadowRoot.querySelectorAll('input[name="modes"]')).toHaveLength(1);
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
