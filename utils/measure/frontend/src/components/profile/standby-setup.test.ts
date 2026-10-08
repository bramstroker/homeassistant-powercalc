import { StandbySetup } from "./standby-setup";
import { capabilities } from "../testing/fixtures";
import type { LightMeasurementRequest, StandbyCalibrationActions, CalibrationJob } from "../../types";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new Event("close")); };
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
const calibration = { description: "Heater", resistance: 2400, calibrated_at: "today", power_meter_fingerprint: "meter" };
const job: CalibrationJob = { id: "job", session_id: "session", status: "running", started_at: new Date().toISOString(), calibration: null, error: null };
function actions(overrides: Partial<StandbyCalibrationActions> = {}): StandbyCalibrationActions {
  return { start: vi.fn(async () => job), status: vi.fn(async () => null), cancel: vi.fn(async () => ({ ...job, status: "cancelled" as const })), loadSaved: vi.fn(async () => null), ...overrides };
}
async function mount(calibrationActions?: StandbyCalibrationActions) {
  const element = new StandbySetup();
  element.request = structuredClone(request);
  element.calibrationActions = calibrationActions;
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
    let saved = false;
    const element = await mount(actions({
      start: async () => { saved = true; return { ...job, status: "completed", calibration }; },
      loadSaved: async () => saved ? calibration : null,
    }));
    await vi.waitFor(() => expect(element.shadowRoot!.querySelector("fieldset")!.disabled).toBe(false));
    const measure = vi.fn();
    element.addEventListener("standby-measure", measure);
    set(element, "load", "calibrate");
    await element.updateComplete;
    set(element, "description", "Heater");
    click(element, "Confirm and measure standby");
    expect(measure).not.toHaveBeenCalled();
    click(element, "Calibrate dummy load");
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Calibration complete"));
    click(element, "Confirm and measure standby");
    expect(measure.mock.calls[0]![0].detail.dummy_load).toEqual({ mode: "reuse", description: "Heater", resistance: 2400 });
  });

  it("reconnects to a background calibration and explicitly cancels it", async () => {
    const api = actions({ status: vi.fn(async () => job) });
    const element = await mount(api);
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Cancel calibration"));
    element.remove();
    expect(api.cancel).not.toHaveBeenCalled();
    const reopened = await mount(api);
    await vi.waitFor(() => expect(reopened.shadowRoot!.textContent).toContain("Cancel calibration"));
    click(reopened, "Cancel calibration");
    await vi.waitFor(() => expect(reopened.shadowRoot!.textContent).toContain("Calibration cancelled"));
    expect(api.cancel).toHaveBeenCalledWith("", "job");
  });

  it("recovers from a transient status failure and an app restart", async () => {
    vi.useFakeTimers();
    const status = vi.fn().mockResolvedValueOnce(job).mockRejectedValueOnce(new Error("Offline")).mockResolvedValue(null);
    const element = await mount(actions({ status }));
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Cancel calibration"));
    await vi.advanceTimersByTimeAsync(1000);
    await element.updateComplete;
    expect(element.shadowRoot!.textContent).toContain("Could not refresh calibration status");
    await vi.advanceTimersByTimeAsync(2000);
    await element.updateComplete;
    expect(element.shadowRoot!.textContent).toContain("Calibration is no longer available");
    expect(element.shadowRoot!.querySelector("fieldset")!.disabled).toBe(false);
  });

  it("reports a failed background calibration", async () => {
    const element = await mount(actions({ status: async () => ({ ...job, status: "failed", error: "Voltage unavailable" }) }));
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Voltage unavailable"));
    expect(element.request).toEqual(request);
  });

  it("cleans up parent state on native close even during measurement", async () => {
    const element = await mount();
    const close = vi.fn();
    element.addEventListener("standby-close", close);
    click(element, "Confirm and measure standby");
    element.shadowRoot!.querySelector("dialog")!.close();
    expect(close).toHaveBeenCalledOnce();
  });

  it.each(["sleep_standby", "sample_count", "sleep_time_sample"])("rejects fractional %s", async name => {
    const element = await mount();
    const measure = vi.fn();
    element.addEventListener("standby-measure", measure);
    set(element, name, "1.5");
    click(element, "Confirm and measure standby");
    expect(measure).not.toHaveBeenCalled();
  });

  it("looks up calibration for the edited meter and clears an incompatible selection", async () => {
    const api = actions({ loadSaved: vi.fn(async meter => meter.type === "hass" && meter.entity_id === "sensor.power" ? calibration : null) });
    const element = await mount(api);
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Reuse saved calibration: Heater"));
    set(element, "load", "reuse");
    set(element, "power", "sensor.other");
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).not.toContain("Reuse saved calibration: Heater"));
    expect(api.loadSaved).toHaveBeenLastCalledWith(expect.objectContaining({ entity_id: "sensor.other" }));
    expect(element.shadowRoot!.querySelector<HTMLSelectElement>('[name="load"]')!.value).toBe("none");
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
