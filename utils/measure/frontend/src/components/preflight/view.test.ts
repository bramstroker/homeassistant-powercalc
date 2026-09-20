import type { PowerMeterDiagnostic, PreflightResponse } from "../../types";
import "./view";
import { PreflightView } from "./view";
import { goodPowerMeterDiagnostic } from "../testing/fixtures";

describe("preflight power meter diagnostics", () => {
  it.each(["measured", "unavailable"] as const)("shows %s standby without blocking start and offers a recheck", async (status) => {
    const element = new PreflightView();
    element.lightLoadProbe = { checked_variations: 1, minimum_aggregate_power_w: 1.2, points: [], standby: { status, power_w: status === "measured" ? 0.3 : null } };
    const recheck = vi.fn();
    element.addEventListener("recheck", recheck);
    document.body.append(element);
    await element.updateComplete;
    expect(element.shadowRoot!.textContent).toContain(status === "measured" ? "0.30 W per light" : "Standby power could not be measured reliably");
    expect(element.shadowRoot!.querySelector<HTMLButtonElement>("button.primary")!.disabled).toBe(false);
    [...element.shadowRoot!.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Recheck setup")!.click();
    expect(recheck).toHaveBeenCalledOnce();
  });

  it("explains preparation and provides immediate feedback while the session initializes", async () => {
    const element = document.createElement("measure-preflight-view") as HTMLElement & {
      confirmationAction: string; busy: boolean; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.confirmationAction = "Start averaging";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("you will explicitly start the measurement on the next screen");
    expect(element.shadowRoot.querySelector("button.primary")?.textContent).toBe("Prepare measurement");

    element.busy = true;
    await element.updateComplete;
    const status = element.shadowRoot.querySelector(".starting");
    expect(status?.getAttribute("role")).toBe("status");
    expect(status?.getAttribute("aria-live")).toBe("polite");
    expect(status?.textContent).toContain("Initializing measurement session");
    expect(status?.textContent).toContain("This can take a few seconds");
    expect((element.shadowRoot.querySelector("button.primary") as HTMLButtonElement).disabled).toBe(true);
    expect((element.shadowRoot.querySelector(".actions button") as HTMLButtonElement).disabled).toBe(true);
  });

  it("separates a setup recheck from starting the session", async () => {
    const element = new PreflightView();
    element.busy = true;
    element.rechecking = true;
    document.body.append(element);
    await element.updateComplete;

    const status = element.shadowRoot!.querySelector(".starting");
    expect(status?.textContent).toContain("Rechecking setup");
    expect(status?.textContent).not.toContain("Initializing measurement session");
    expect(element.shadowRoot!.querySelector("button.primary")?.textContent).toBe("Rechecking\u2026");
  });

  it("blocks starting on results left behind by a failed recheck", async () => {
    const element = new PreflightView();
    element.stale = true;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot!.textContent).toContain("The setup check did not complete");
    expect(element.shadowRoot!.querySelector<HTMLButtonElement>("button.primary")!.disabled).toBe(true);
    const recheck = [...element.shadowRoot!.querySelectorAll<HTMLButtonElement>("button")]
      .find(button => button.textContent === "Recheck setup")!;
    expect(recheck.disabled).toBe(false);
  });

  it("keeps direct measurements as a single Start measurement action", async () => {
    const element = document.createElement("measure-preflight-view") as HTMLElement & {
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector("button.primary")?.textContent).toBe("Start measurement");
    expect(element.shadowRoot.textContent).not.toContain("explicitly start");
  });

  it("shows the same quality details before a measurement starts", async () => {
    const element = document.createElement("measure-preflight-view") as HTMLElement & {
      powerMeterDiagnostic: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.powerMeterDiagnostic = goodPowerMeterDiagnostic;
    document.body.append(element);
    await element.updateComplete;

    const diagnostic = element.shadowRoot.querySelector("measure-power-meter-diagnostic") as HTMLElement & { updateComplete: Promise<boolean>; shadowRoot: ShadowRoot };
    await diagnostic.updateComplete;
    expect(diagnostic.getAttribute("heading")).toBe("Measurement device quality");
    expect(diagnostic.shadowRoot.textContent).toContain("1.8 s");
    expect(diagnostic.shadowRoot.textContent).toContain("Good");
  });

  it("shows every completed low-load probe point and measured power", async () => {
    const element = document.createElement("measure-preflight-view") as HTMLElement & {
      lightLoadProbe: NonNullable<PreflightResponse["light_load_probe"]>;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.lightLoadProbe = {
      checked_variations: 2,
      minimum_aggregate_power_w: 0.9,
      points: [
        { label: "Color 120° / 100% saturation · brightness 1", mode: "hs", power_w: 0.9 },
        { label: "Color temperature 454 mired · brightness 1", mode: "color_temp", power_w: 1.25 },
      ],
    };
    document.body.append(element);
    await element.updateComplete;

    const results = element.shadowRoot.querySelector('[aria-label="Low-load light check results"]');
    expect(results?.textContent).toContain("Low-load light check passed");
    expect(results?.textContent).toContain("Color 120° / 100% saturation · brightness 1");
    expect(results?.textContent).toContain("0.900 W aggregate");
    expect(results?.textContent).toContain("Color temperature 454 mired · brightness 1");
    expect(results?.textContent).toContain("1.250 W aggregate");
  });
});
