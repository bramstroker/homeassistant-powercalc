import type { OperatingPoint, SessionSnapshot } from "../../types";
import "./running-view";

describe("running view", () => {
  it("stops averaging through the same action as recording and disables repeated requests", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; busy: boolean; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", mode: "Averaging", progress: { completed: 6, total: 60 } };
    document.body.append(element);
    await element.updateComplete;
    const cancel = vi.fn();
    element.addEventListener("cancel", cancel);
    const stop = element.shadowRoot.querySelector<HTMLButtonElement>(".actions button")!;
    expect(stop.textContent).toBe("Stop measurement");
    expect(stop.classList.contains("primary")).toBe(true);
    stop.click();
    expect(cancel).toHaveBeenCalledOnce();

    element.busy = true;
    await element.updateComplete;
    expect(element.shadowRoot.querySelector<HTMLButtonElement>(".actions button")?.disabled).toBe(true);
    element.busy = false;
    element.snapshot = { ...element.snapshot, state: "cancelling" };
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".actions button")?.textContent).toBe("Stopping…");
    expect(element.shadowRoot.querySelector<HTMLButtonElement>(".actions button")?.disabled).toBe(true);

    element.snapshot = { ...element.snapshot, state: "awaiting_confirmation" };
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".actions button")?.textContent).toBe("Cancel measurement");
  });

  it("shows an indeterminate preparation state instead of zero progress", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", phase: "Preparing measurement devices" };
    document.body.append(element);
    await element.updateComplete;

    const preparation = element.shadowRoot.querySelector(".preparation");
    expect(preparation?.getAttribute("role")).toBe("status");
    expect(preparation?.getAttribute("aria-live")).toBe("polite");
    expect(preparation?.textContent).toContain("Preparing measurement devices");
    expect(element.shadowRoot.querySelector("#running-title")?.textContent).toBe("Preparing measurement");
    expect(element.shadowRoot.querySelector(".preparation-spinner")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".preparation-bar")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".value")).toBeNull();
    expect(element.shadowRoot.querySelector("progress")).toBeNull();
  });

  it("shows a dedicated ready card with the requested confirmation action", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; confirmationAction: string; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "awaiting_confirmation",
      confirmation_message: "Switch on the test signal, then start recording.",
    };
    element.confirmationAction = "Start recording";
    document.body.append(element);
    await element.updateComplete;

    const ready = element.shadowRoot.querySelector(".ready-card");
    const announcement = element.shadowRoot.querySelector(".ready-announcement");
    expect(announcement).toBeTruthy();
    expect(announcement?.getAttribute("role")).toBe("status");
    expect(announcement?.getAttribute("aria-live")).toBe("polite");
    expect(ready?.textContent).toContain("Switch on the test signal, then start recording.");
    expect(ready?.querySelector("button.confirm")?.textContent).toBe("Start recording");
    expect(element.shadowRoot.querySelector(".instrument")).toBeNull();
    expect(element.shadowRoot.querySelector("progress")).toBeNull();
  });

  it("renders speaker confirmation as a high-volume warning", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; confirmationAction: string; warningConfirmation: boolean;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "awaiting_confirmation",
      confirmation_message: "Speaker measurements can become very loud.",
    };
    element.confirmationAction = "Start speaker measurement";
    element.warningConfirmation = true;
    document.body.append(element);
    await element.updateComplete;

    const warning = element.shadowRoot.querySelector(".ready-card.warning");
    expect(warning).toBeTruthy();
    expect(warning?.querySelector(".ready-announcement")?.getAttribute("role")).toBe("alert");
    expect(warning?.textContent).toContain("High volume warning");
    expect(warning?.textContent).toContain("Protect your hearing");
    expect(warning?.querySelector(".ready-icon svg")).toBeTruthy();
  });

  it("shows progress, phase, connection state, and cancellation", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      connected: boolean;
      diagnosticsUrl: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", phase: "Brightness", mode: "brightness", progress: { completed: 25, total: 100, estimated_remaining_seconds: 120 } };
    element.connected = true;
    element.diagnosticsUrl = "http://ha.local/ingress/api/sessions/session-1/diagnostics";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("25%");
    expect(element.shadowRoot.textContent).toContain("Brightness");
    expect(element.shadowRoot.textContent).toContain("Live");
    expect(element.shadowRoot.querySelector("progress")?.value).toBe(25);
    expect(element.shadowRoot.querySelector("button")?.textContent).toContain("Cancel measurement");
    const diagnostics = element.shadowRoot.querySelector(".diagnostics-download a") as HTMLAnchorElement;
    expect(diagnostics.textContent).toBe("Download diagnostics");
    expect(diagnostics.href).toBe(element.diagnosticsUrl);
    expect(element.shadowRoot.querySelector(".diagnostics-download")?.textContent).toContain("snapshot and logs");
  });

  it("shows sub-one-percent progress and skipped readings", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", mode: "brightness", progress: { completed: 1, total: 300, skipped: 1 } };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".value")?.textContent).toContain("<1%");
    expect(element.shadowRoot.querySelector("progress")?.value).toBeCloseTo(1 / 300 * 100);
    expect(element.shadowRoot.textContent).toContain("1 / 300");
    expect(element.shadowRoot.textContent).toContain("Skipped");
  });

  it("draws a live power chart from streamed samples", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; samples: number[]; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", progress: { completed: 1, total: 10 } };
    element.samples = [4.2, 5.1, 4.8];
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".chart")).toBeTruthy();
    expect(element.shadowRoot.querySelector("svg.spark polyline.line")?.getAttribute("points")).toContain(",");
    expect(element.shadowRoot.querySelector(".chart-head strong")?.textContent).toContain("4.8");
    expect(element.shadowRoot.querySelector(".chart-scale")?.textContent).toContain("peak 5.1 W");
  });

  it("keeps live samples visible while numeric progress is not available yet", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; samples: number[]; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", phase: "Stabilizing device" };
    element.samples = [4.2, 4.3];
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".preparation")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".chart")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".value")).toBeNull();
  });

  it("shows wattage, resistance, and voltage while calibrating a dummy load", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "running",
      phase: "Calibrating resistive dummy load",
      mode: "Calibrating resistive dummy load",
      progress: { completed: 3, total: 20 },
      calibration_sample: { power: 60.125, resistance: 881.234, voltage: 230.25 },
    };
    document.body.append(element);
    await element.updateComplete;

    const calibration = element.shadowRoot.querySelector('[aria-label="Live dummy-load calibration reading"]');
    expect(calibration?.textContent).toContain("Wattage60.13 W");
    expect(calibration?.textContent).toContain("Resistance881.23 Ω");
    expect(calibration?.textContent).toContain("Voltage230.25 V");
  });

  it.each([
    [
      { type: "light", on: true, brightness: 128, color_temp_mired: 370, hue: 32_768, saturation: 128 } as OperatingPoint,
      ["Brightness 50%", "Color temp 2703 K", "Hue 180°", "Saturation 50%"],
    ],
    [{ type: "light", on: false } as OperatingPoint, ["Off"]],
    [{ type: "speaker", volume: 40, muted: false } as OperatingPoint, ["Volume 40%"]],
    [{ type: "speaker", volume: 0, muted: true } as OperatingPoint, ["Muted"]],
    [{ type: "fan", percentage: 65, on: true } as OperatingPoint, ["Fan speed 65%"]],
    [{ type: "charging", battery_level: 72, charging: true } as OperatingPoint, ["Battery 72%", "Charging"]],
  ])("renders a compact current measurement point for %#", async (operatingPoint, expected) => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", operating_point: operatingPoint };
    document.body.append(element);
    await element.updateComplete;

    const state = element.shadowRoot.querySelector(".operating-point");
    expect(element.shadowRoot.querySelector(".preparation")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".value")).toBeNull();
    expect(state?.getAttribute("aria-live")).toBe("polite");
    expect(state?.textContent).toContain("Current measurement point");
    for (const value of expected) expect(state?.textContent).toContain(value);
  });

  it.each([
    [
      { type: "light", on: true, brightness: 128, color_temp_mired: 370, hue: 32_768, saturation: 128, effect: "candle" } as OperatingPoint,
      ["brightness", "color-temp", "hue", "saturation", "effect"],
    ],
    [{ type: "light", on: false } as OperatingPoint, ["off"]],
    [{ type: "speaker", volume: 40, muted: false } as OperatingPoint, ["volume"]],
    [{ type: "speaker", volume: 0, muted: true } as OperatingPoint, ["muted"]],
    [{ type: "fan", percentage: 65, on: true } as OperatingPoint, ["fan-speed"]],
    [{ type: "fan", percentage: 0, on: false } as OperatingPoint, ["off"]],
    [{ type: "charging", battery_level: 72, charging: true } as OperatingPoint, ["battery", "charging"]],
    [{ type: "charging", battery_level: 25, charging: false } as OperatingPoint, ["battery", "not-charging"]],
  ])("adds an icon to every operating-point chip for %#", async (operatingPoint, icons) => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", operating_point: operatingPoint };
    document.body.append(element);
    await element.updateComplete;

    const chips = [...element.shadowRoot.querySelectorAll(".state-chip")];
    const renderedIcons = [...element.shadowRoot.querySelectorAll("[data-state-icon]")];
    expect(renderedIcons.map((icon) => icon.getAttribute("data-state-icon"))).toEqual(icons);
    expect(renderedIcons).toHaveLength(chips.length);
    for (const icon of renderedIcons) expect(icon.getAttribute("aria-hidden")).toBe("true");
  });

  it("hides the power chart until the first sample arrives", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "awaiting_confirmation" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".chart")).toBeNull();
  });

  it("shows a live sample count for an open-ended recording", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", mode: "Recording", progress: { completed: 7, total: 0 } };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".value")?.textContent).toContain("7");
    expect(element.shadowRoot.textContent).toContain("samples");
    expect(element.shadowRoot.textContent).toContain("Until stopped");
    const stop = [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Stop recording"));
    expect(stop).toBeTruthy();
    expect(element.shadowRoot.querySelector("button.danger")).toBeNull();
  });

  it("shows the latest tracked entity states during a complex recording", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "running",
      mode: "Recording",
      progress: { completed: 8, total: 0 },
      entity_states: { "vacuum.robot": "cleaning", "sensor.robot_battery": "42" },
    };
    document.body.append(element);
    await element.updateComplete;

    const states = element.shadowRoot.querySelector(".entity-states");
    expect(states?.textContent).toContain("Tracked entities");
    expect(states?.textContent).toContain("vacuum.robot");
    expect(states?.textContent).toContain("cleaning");
    expect(states?.textContent).toContain("sensor.robot_battery");
    expect(states?.textContent).toContain("42");
  });

  it("labels average progress in seconds", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", mode: "Averaging", progress: { completed: 12, total: 60, estimated_remaining_seconds: 48 } };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Seconds");
    expect(element.shadowRoot.textContent).toContain("12 / 60");
  });

  it("keeps the log collapsed by default and opens it as an overlay on toggle", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; logs: string[]; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", progress: { completed: 1, total: 10 } };
    element.logs = ["First log", "Second log"];
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".log-overlay")).toBeNull();
    const toggle = element.shadowRoot.querySelector(".log-toggle") as HTMLButtonElement;
    expect(toggle.textContent).toContain("View log");
    expect(toggle.textContent).toContain("2");

    toggle.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".log-overlay")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".log-overlay")?.textContent).toContain("Second log");
  });

  it("presents discarded readings as warnings in the page and log panel", async () => {
    const warning = "Discarding measurement: 0 watt was read from the power meter";
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot; logs: string[]; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", progress: { completed: 0, total: 2 }, warnings: [warning] };
    element.logs = [warning];
    document.body.append(element);
    await element.updateComplete;

    const notice = element.shadowRoot.querySelector(".notice.warning");
    expect(notice?.getAttribute("role")).toBe("alert");
    expect(notice?.textContent).toContain(warning);

    (element.shadowRoot.querySelector(".log-toggle") as HTMLButtonElement).click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".log p.warning")?.textContent).toContain(warning);
  });

  it("auto-scrolls the log container when new log lines arrive", async () => {
    const element = document.createElement("measure-running-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      connected: boolean;
      logs: string[];
      logOpen: boolean;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "running", progress: { completed: 1, total: 10 } };
    element.logs = ["First log"];
    element.logOpen = true;
    document.body.append(element);
    await element.updateComplete;

    const logContainer = element.shadowRoot.querySelector(".log") as HTMLDivElement;
    Object.defineProperty(logContainer, "scrollHeight", { value: 240, configurable: true });
    Object.defineProperty(logContainer, "scrollTop", { value: 0, writable: true, configurable: true });

    element.logs = [...element.logs, "Second log"];
    await element.updateComplete;

    expect(logContainer.scrollTop).toBe(240);
  });
});
