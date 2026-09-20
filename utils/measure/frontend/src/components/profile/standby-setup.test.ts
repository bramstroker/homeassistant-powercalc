import { StandbySetup } from "./standby-setup";
import { capabilities } from "../testing/fixtures";
import type { LightMeasurementRequest } from "../../types";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
});

const request: LightMeasurementRequest = {
  measure_type: "light", model_id: "test", product_name: "Test", measure_device: "Meter",
  generate_model: true, resume_policy: "new", modes: ["brightness"],
  controller: { type: "hass_multi", entity_ids: ["light.one", "light.two"] },
  power_meter: { type: "hass", entity_id: "sensor.power", voltage_entity_id: "sensor.voltage" },
  multiple_light_count: 2, parameters: capabilities.defaults,
};
async function mount() {
  const element = new StandbySetup();
  element.request = structuredClone(request);
  document.body.append(element);
  await element.updateComplete;
  return element;
}
function set(element: StandbySetup, name: string, value: string) {
  const input = element.shadowRoot!.querySelector<HTMLInputElement>(`[name="${name}"]`)!;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}
function click(element: StandbySetup, label: string) {
  [...element.shadowRoot!.querySelectorAll("button")].find(button => button.textContent === label)!.click();
}

describe("standby setup", () => {
  it("prefills and submits changed entities, count and timing without mutating the session", async () => {
    const element = await mount();
    const measure = vi.fn();
    element.addEventListener("standby-measure", measure);
    set(element, "entities", "light.two");
    set(element, "bulbs", "1");
    set(element, "sleep_standby", "30");
    click(element, "Confirm and measure standby");
    expect(measure.mock.calls[0]![0].detail).toMatchObject({
      controller: { type: "hass", entity_id: "light.two" }, multiple_light_count: 1,
      parameters: { sleep_standby: 30, sample_count: 5, sleep_time_sample: 2 },
    });
    expect(element.request).toEqual(request);
  });

  it("cancels without measuring", async () => {
    const element = await mount();
    const measure = vi.fn();
    const close = vi.fn();
    element.addEventListener("standby-measure", measure);
    element.addEventListener("standby-close", close);
    click(element, "Cancel");
    expect(close).toHaveBeenCalledOnce();
    expect(measure).not.toHaveBeenCalled();
  });

  it("requires calibration and a separate reconnect confirmation", async () => {
    const element = await mount();
    const measure = vi.fn();
    element.addEventListener("standby-measure", measure);
    element.calibrate = vi.fn(async () => ({ description: "Heater", resistance: 2400, calibrated_at: "today" }));
    set(element, "load", "calibrate");
    await element.updateComplete;
    set(element, "description", "Heater");
    click(element, "Confirm and measure standby");
    expect(measure).not.toHaveBeenCalled();
    click(element, "Calibrate dummy load");
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Calibration complete"));
    expect(measure).not.toHaveBeenCalled();
    click(element, "Confirm and measure standby");
    expect(measure.mock.calls[0]![0].detail.dummy_load).toEqual({ mode: "reuse", description: "Heater", resistance: 2400 });
  });

  it("preserves the setup after calibration failure", async () => {
    const element = await mount();
    element.calibrate = vi.fn(async () => { throw new Error("Voltage unavailable"); });
    set(element, "load", "calibrate");
    await element.updateComplete;
    set(element, "description", "Heater");
    click(element, "Calibrate dummy load");
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Voltage unavailable"));
    expect(element.request).toEqual(request);
  });
  it("shows elapsed time and keeps the result in the dialog", async () => {
    vi.useFakeTimers();
    const element = await mount();
    click(element, "Confirm and measure standby");
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector("dialog")!.open).toBe(true);
    expect(element.shadowRoot!.querySelector("progress")).not.toBeNull();
    expect(element.shadowRoot!.textContent).toContain("Allow about 20s");
    await vi.advanceTimersByTimeAsync(22000);
    expect(element.shadowRoot!.textContent).toContain("Elapsed: 22s");
    expect(element.shadowRoot!.textContent).toContain("Still waiting for the meter");
    element.measurementMessage = "Measured 0.32 W per light.";
    element.measuring = false;
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector("progress")).toBeNull();
    expect(element.shadowRoot!.textContent).toContain("Measured 0.32 W per light.");
    await vi.advanceTimersByTimeAsync(3000);
    expect(element.shadowRoot!.textContent).toContain("Elapsed: 22s");
    click(element, "Measure again");
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector("fieldset")!.hidden).toBe(false);
  });

});
