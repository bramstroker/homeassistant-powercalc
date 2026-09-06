import type { SessionSnapshot } from "../../types";
import "./view";

describe("result view", () => {
  it.each(["completed", "failed", "cancelled", "resumable"] as const)("offers diagnostics for a %s session without generated files", async (state) => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      diagnosticsUrl: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state };
    element.diagnosticsUrl = "http://ha.local/ingress/api/sessions/session-1/diagnostics";
    document.body.append(element);
    await element.updateComplete;

    const diagnostics = element.shadowRoot.querySelector(".diagnostics-download a") as HTMLAnchorElement;
    expect(diagnostics.textContent).toBe("Download diagnostics");
    expect(diagnostics.href).toBe(element.diagnosticsUrl);
    expect(element.shadowRoot.querySelector(".diagnostics-download")?.textContent).toContain("snapshot and logs");
  });

  it("keeps failed results focused on the actionable error", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      files: { name: string; size: number; media_type: string }[];
      plotCollection: { partial: boolean; plots: never[]; warnings: string[] };
      diagnosticsUrl: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "failed",
      error: "Aborting measurement session after repeated 0 W readings. The power meter may not resolve this low load. See https://docs.powercalc.nl/contributing/measure/troubleshooting/ for troubleshooting guidance.",
    };
    element.files = [{ name: "brightness.csv", size: 10, media_type: "text/csv" }];
    element.plotCollection = { partial: true, plots: [], warnings: ["Could not plot brightness.csv"] };
    element.diagnosticsUrl = "http://ha.local/ingress/api/sessions/session-1/diagnostics";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".notice.error")?.textContent).toContain("use a more sensitive meter.");
    const troubleshootingLink = element.shadowRoot.querySelector(".notice.error a") as HTMLAnchorElement;
    expect(troubleshootingLink.textContent).toBe("Troubleshooting guide");
    expect(troubleshootingLink.href).toBe("https://docs.powercalc.nl/contributing/measure/troubleshooting/");
    expect(element.shadowRoot.textContent).toContain("correct the problem");
    expect(element.shadowRoot.textContent).not.toContain("Could not plot");
    expect(element.shadowRoot.textContent).not.toContain("Generated files");
    expect(element.shadowRoot.textContent).not.toContain("Download all");
    expect(element.shadowRoot.querySelector(".diagnostics-download a")).toBeTruthy();
  });

  it("does not linkify a trusted URL embedded in an arbitrary error", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "failed",
      error: "Unexpected response from https://malicious.example/https://docs.powercalc.nl/contributing/measure/troubleshooting/",
    };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".notice.error")?.textContent).toContain("malicious.example");
    expect(element.shadowRoot.querySelector(".notice.error a")).toBeNull();
  });

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

    const contribution = element.shadowRoot.querySelector(".contribution");
    expect(contribution?.textContent).toContain("Prepare the profile");
    expect(element.shadowRoot.querySelector(".contribution-next")).toBeNull();
  });


  it.each(["failed", "cancelled", "resumable"] as const)("does not suggest contribution for a %s session", async (state) => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".contribution-next")).toBeNull();
  });

  it("renders a summary readout for a file-less measurement", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot; files: { name: string; size: number; media_type: string }[];
      fileUrl: (name: string) => string; downloadAll: () => void;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed", summary: { "Average power": "42.3 W", "Duration": "30 s" } };
    element.files = [];
    element.fileUrl = (name) => name;
    element.downloadAll = () => {};
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".readout")?.textContent).toContain("42.3 W");
    expect(element.shadowRoot.querySelector("#result-title")?.textContent).toContain("Measurement complete");
    expect(element.shadowRoot.textContent).not.toContain("No downloadable files");
    expect(element.shadowRoot.querySelector(".contribution")?.textContent).toContain("Prepare the profile");
  });

  it("separates recording analysis from measurement results", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot; updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = {
      state: "completed",
      summary: {
        "Samples recorded": "39",
        Duration: "160 s",
        "Recording analysis": "Fixed power profile created",
        "Analysed feature": "input_select.powercalc_test_state.state",
        "Validation MAE": "0.02 W",
        "Validation coverage": "100%",
      },
      warnings: ["Analysis completed with a warning"],
    };
    document.body.append(element);
    await element.updateComplete;

    const measurement = element.shadowRoot.querySelector('[aria-label="Measurement result"]');
    expect(measurement?.textContent).toContain("39");
    expect(measurement?.textContent).not.toContain("Fixed power profile created");
    const analysis = element.shadowRoot.querySelector(".analysis-panel");
    expect(analysis?.textContent).toContain("A fixed power profile was created.");
    expect(analysis?.textContent).toContain("input_select.powercalc_test_state");
    const details = analysis?.querySelector('[aria-label="Recording analysis details"]');
    expect(details?.textContent).toContain("Typical difference");
    expect(details?.textContent).toContain("Data coverage");
    expect(details?.querySelectorAll(".analysis-help")).toHaveLength(3);
    expect(element.shadowRoot.querySelector('.notice[role="status"]')?.textContent).toContain("warning");
  });

  it("can run the analyser again without starting a new measurement", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot; canAnalyse: boolean; analysisComplete: boolean; busy: boolean;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed", summary: { "Recording analysis": "More data needed" } };
    element.canAnalyse = true;
    const analyse = vi.fn();
    element.addEventListener("analyse", analyse);
    document.body.append(element);
    await element.updateComplete;

    const button = element.shadowRoot.querySelector(".analysis-retry button") as HTMLButtonElement;
    expect(element.shadowRoot.querySelector(".analysis-retry")?.textContent).toContain("No new measurement is needed");
    button.click();
    expect(analyse).toHaveBeenCalledOnce();

    element.busy = true;
    await element.updateComplete;
    expect((element.shadowRoot.querySelector(".analysis-retry button") as HTMLButtonElement).disabled).toBe(true);
    expect(element.shadowRoot.querySelector(".analysis-retry")?.textContent).toContain("Analysing…");

    element.busy = false;
    element.analysisComplete = true;
    await element.updateComplete;
    expect(element.shadowRoot.querySelector('.analysis-retry p[role="status"]')?.textContent).toContain("Recording analysed again");
  });

  it("opens analyser and model JSON in an in-app viewer", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      files: { name: string; size: number; media_type: string }[];
      inspectJsonFile: (name: string) => Promise<unknown>;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    const inspectJsonFile = vi.fn(async (name: string) => ({ name, sample_count: 228 }));
    element.snapshot = { state: "completed" };
    element.files = [
      { name: "analyser.json", size: 100, media_type: "application/json" },
      { name: "profile/model.json", size: 200, media_type: "application/json" },
      { name: "record.jsonl", size: 300, media_type: "application/json" },
    ];
    element.inspectJsonFile = inspectJsonFile;
    document.body.append(element);
    await element.updateComplete;

    const buttons = [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".inspect-file")];
    expect(buttons.map((button) => button.getAttribute("aria-label"))).toEqual([
      "View analyser.json",
      "View profile/model.json",
    ]);
    buttons[0]?.click();
    await vi.waitFor(() => expect(element.shadowRoot.querySelector(".json-dialog pre")?.textContent).toContain('"sample_count": 228'));
    expect(inspectJsonFile).toHaveBeenCalledWith("analyser.json");
    (element.shadowRoot.querySelector(".json-dialog-header button") as HTMLButtonElement).click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector('[role="dialog"]')).toBeNull();
  });

  it("shows JSON inspection failures inside the viewer", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      files: { name: string; size: number; media_type: string }[];
      inspectJsonFile: (name: string) => Promise<unknown>;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed" };
    element.files = [{ name: "analysis.json", size: 100, media_type: "application/json" }];
    element.inspectJsonFile = async () => { throw new Error("File could not be read"); };
    document.body.append(element);
    await element.updateComplete;
    (element.shadowRoot.querySelector(".inspect-file") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(element.shadowRoot.querySelector('.json-dialog [role="alert"]')?.textContent).toContain("File could not be read"));
  });

  it("renders partial plots and offers a PNG download", async () => {
    const context = {
      setTransform: vi.fn(), clearRect: vi.fn(), fillRect: vi.fn(), beginPath: vi.fn(), moveTo: vi.fn(),
      lineTo: vi.fn(), stroke: vi.fn(), arc: vi.fn(), fill: vi.fn(), fillText: vi.fn(), save: vi.fn(),
      restore: vi.fn(), translate: vi.fn(), rotate: vi.fn(), measureText: vi.fn(() => ({ width: 10 })),
    } as unknown as CanvasRenderingContext2D;
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,plot");
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      plotCollection: {
        partial: boolean;
        warnings: string[];
        plots: {
          id: string; title: string; kind: "scatter"; x_label: string; y_label: string; source: string;
          series: { label: null; color: string; points: { x: number; y: number; color: null }[] }[];
        }[];
      };
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "cancelled" };
    element.plotCollection = {
      partial: true,
      warnings: [],
      plots: [{
        id: "brightness", title: "Brightness", kind: "scatter", x_label: "Brightness", y_label: "Power (W)",
        source: "LCT010/brightness.csv",
        series: [{ label: null, color: "#5488e8", points: [{ x: 1, y: 0.5, color: null }] }],
      }],
    };
    document.body.append(element);
    await element.updateComplete;

    const plot = element.shadowRoot.querySelector("measure-result-plot") as HTMLElement & {
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    await plot.updateComplete;
    expect(plot.shadowRoot.textContent).toContain("Partial result");
    (plot.shadowRoot.querySelector(".plot-download") as HTMLButtonElement).click();
    expect(click).toHaveBeenCalled();
  });
});
