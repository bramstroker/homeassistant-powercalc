import type { PowerMeterDiagnostic } from "../types";
import "./preflight-view";
import { goodPowerMeterDiagnostic } from "./test-fixtures";

describe("preflight power meter diagnostics", () => {
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
});
