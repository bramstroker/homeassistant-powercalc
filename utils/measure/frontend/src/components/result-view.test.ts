import type { ContributionPreview, SessionSnapshot } from "../types";
import "./result-view";

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
      error: "Use a more sensitive meter. See https://docs.powercalc.nl/contributing/measure/troubleshooting/ for troubleshooting guidance.",
    };
    element.files = [{ name: "brightness.csv", size: 10, media_type: "text/csv" }];
    element.plotCollection = { partial: true, plots: [], warnings: ["Could not plot brightness.csv"] };
    element.diagnosticsUrl = "http://ha.local/ingress/api/sessions/session-1/diagnostics";
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".notice.error")?.textContent).toContain("Use a more sensitive meter.");
    const troubleshootingLink = element.shadowRoot.querySelector(".notice.error a") as HTMLAnchorElement;
    expect(troubleshootingLink.textContent).toBe("Troubleshooting guide");
    expect(troubleshootingLink.href).toBe("https://docs.powercalc.nl/contributing/measure/troubleshooting/");
    expect(element.shadowRoot.textContent).toContain("correct the problem");
    expect(element.shadowRoot.textContent).not.toContain("Could not plot");
    expect(element.shadowRoot.textContent).not.toContain("Generated files");
    expect(element.shadowRoot.textContent).not.toContain("Download all");
    expect(element.shadowRoot.querySelector(".diagnostics-download a")).toBeTruthy();
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
    expect(contribution?.textContent).toContain("Contribute your measurement");
    // Without an eligible GitHub draft, the manual method is selected by default.
    const nextSteps = element.shadowRoot.querySelector(".contribution-next");
    expect(nextSteps?.textContent).toContain("Download and inspect the generated files");
    expect(nextSteps?.textContent).toContain("profile_library/<manufacturer>/<model>/");
    const guide = nextSteps?.querySelector("a") as HTMLAnchorElement;
    expect(guide.href).toBe("https://docs.powercalc.nl/contributing/measure/output/");
    expect(guide.target).toBe("_blank");
    expect(guide.rel).toContain("noopener");
  });

  it("defaults to the GitHub method for an eligible draft and offers manual as an alternative", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      files: { name: string; size: number; media_type: string }[];
      fileUrl: (name: string) => string;
      downloadAll: () => void;
      contributionAuth: { connected: boolean; identity: { login: string } };
      contributionPreview: {
        eligible: boolean;
        repository: string;
        base_branch: string;
        manufacturer_name: string;
        manufacturer_directory: string;
        manufacturer_library_url?: string;
        model_id: string;
        product_name: string;
        contributor: string;
        device_info: Record<string, string>;
        home_assistant: Record<string, string>;
        notes: string;
        files: { path: string; rendered_json: Record<string, string> }[];
        model_json: Record<string, string>;
        commit_message: string;
        pr_title: string;
        pr_body: string;
        branch_name: string;
        warnings: string[];
      };
      contributionResult: { status: string; pull_request_url: string };
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed" };
    element.files = [{ name: "model.json", size: 5678, media_type: "application/json" }];
    element.fileUrl = (name) => `/download/${name}`;
    element.downloadAll = () => {};
    element.contributionAuth = { connected: true, identity: { login: "octocat" } };
    element.contributionPreview = {
      eligible: true,
      repository: "bramstroker/homeassistant-powercalc",
      base_branch: "master",
      manufacturer_name: "Signify",
      manufacturer_directory: "signify",
      manufacturer_library_url: "https://library.powercalc.nl/manufacturers/signify",
      model_id: "LCT010",
      product_name: "Hue lamp",
      contributor: "octocat",
      device_info: { device: "light.desk" },
      home_assistant: { version: "2026.7" },
      notes: "Measured through the HA app.",
      files: [{ path: "profile_library/signify/LCT010/model.json", rendered_json: { name: "Hue lamp" } }],
      model_json: { name: "Hue lamp" },
      commit_message: "Add Signify LCT010",
      pr_title: "Add Signify LCT010",
      pr_body: "Adds a measured profile.",
      branch_name: "measure/signify-lct010",
      warnings: [],
    };
    element.contributionResult = { status: "success", pull_request_url: "https://github.com/bramstroker/homeassistant-powercalc/pull/1" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".download-all")).toBeTruthy();
    // GitHub is the default method for an eligible draft; the manual panel is not shown yet.
    const cards = Array.from(element.shadowRoot.querySelectorAll(".method-card")) as HTMLButtonElement[];
    expect(cards.map((card) => card.textContent)).toEqual([
      expect.stringContaining("GitHub pull request"),
      expect.stringContaining("Manual contribution"),
      expect.stringContaining("Add to this installation"),
    ]);
    const [githubCard, manualCard, localCard] = cards as [HTMLButtonElement, HTMLButtonElement, HTMLButtonElement];
    expect(githubCard.getAttribute("aria-checked")).toBe("true");
    expect(localCard.disabled).toBe(true); // local install is not available yet
    expect(element.shadowRoot.querySelector(".contribution-next")).toBeNull();
    const automatic = element.shadowRoot.querySelector(".contribution-auto");
    expect(automatic?.textContent).toContain("Connected to GitHub as octocat");
    expect(automatic?.textContent).toContain("profile_library/signify/LCT010/model.json");
    expect(automatic?.textContent).toContain("Add Signify LCT010");
    expect(automatic?.textContent).not.toContain("aliases");
    const manufacturerLink = element.shadowRoot.querySelector(".manufacturer-library-link") as HTMLAnchorElement;
    expect(manufacturerLink.href).toBe("https://library.powercalc.nl/manufacturers/signify");
    expect(element.shadowRoot.textContent).toContain("without repeating the manufacturer");

    const previewed = new Promise<unknown>((resolve) => element.addEventListener("contribution-preview", (event) => resolve((event as CustomEvent).detail)));
    (element.shadowRoot.querySelector('input[name="manufacturer_directory"]') as HTMLInputElement).value = "philips";
    (element.shadowRoot.querySelector(".contribution-form") as HTMLFormElement).requestSubmit();
    expect(await previewed).toMatchObject({ manufacturer_directory: "philips" });

    const submit = element.shadowRoot.querySelector(".contribution-auto button.primary") as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    (element.shadowRoot.querySelector('input[name="confirm_contribution"]') as HTMLInputElement).click();
    await element.updateComplete;
    expect((element.shadowRoot.querySelector(".contribution-auto button.primary") as HTMLButtonElement).disabled).toBe(false);
    const submitted = new Promise<unknown>((resolve) => element.addEventListener("contribution-submit", (event) => resolve((event as CustomEvent).detail)));
    (element.shadowRoot.querySelector(".contribution-auto button.primary") as HTMLButtonElement).click();
    expect(await submitted).toMatchObject({ confirmed: true, manufacturer_directory: "philips" });
    expect((element.shadowRoot.querySelector(".success-link") as HTMLAnchorElement).href).toBe(element.contributionResult.pull_request_url);

    // Switching to the manual method reveals the download guide instead of the GitHub form.
    manualCard.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".contribution-auto")).toBeNull();
    expect(element.shadowRoot.querySelector(".contribution-next")?.textContent).toContain("Read the contribution guide");
  });

  it("shows product-name contribution errors beside the naming guidance", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      contributionAuth: { connected: boolean; identity: { login: string } };
      contributionDraft: ContributionPreview;
      contributionError: string;
      contributionErrorField: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed" };
    element.contributionAuth = { connected: true, identity: { login: "octocat" } };
    element.contributionDraft = {
      eligible: true,
      repository: "bramstroker/homeassistant-powercalc",
      base_branch: "master",
      manufacturer_name: "Signify",
      manufacturer_directory: "",
      model_id: "LCT010",
      product_name: "Signify Hue lamp",
      contributor: "octocat",
      device_info: {},
      home_assistant: {},
      notes: "",
      files: [],
      commit_message: "",
      pr_title: "",
      pr_body: "",
      branch_name: "",
      warnings: [],
    };
    element.contributionError = "Product name must not start with the manufacturer";
    element.contributionErrorField = "product_name";
    document.body.append(element);
    await element.updateComplete;

    const productName = element.shadowRoot.querySelector('input[name="product_name"]') as HTMLInputElement;
    expect(productName.getAttribute("aria-invalid")).toBe("true");
    expect(productName.parentElement?.textContent).toContain(element.contributionError);
    expect(element.shadowRoot.querySelector(".manufacturer-library-link")).toBeNull();
  });

  it("asks to open settings on the GitHub section when GitHub is not connected", async () => {
    const element = document.createElement("measure-result-view") as HTMLElement & {
      snapshot: SessionSnapshot;
      contributionAuth: { connected: boolean };
      contributionDraft: { eligible: boolean; manufacturer_name: string; manufacturer_directory: string; model_id: string; product_name: string; contributor: string; notes: string; device_info: Record<string, string>; home_assistant: Record<string, string> };
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed" };
    element.contributionAuth = { connected: false };
    element.contributionDraft = {
      eligible: true, manufacturer_name: "Signify", manufacturer_directory: "signify", model_id: "LCT010",
      product_name: "Hue lamp", contributor: "", notes: "", device_info: {}, home_assistant: {},
    };
    document.body.append(element);
    await element.updateComplete;

    const opened = new Promise<unknown>((resolve) => element.addEventListener("open-settings", (event) => resolve((event as CustomEvent).detail)));
    const button = [...element.shadowRoot.querySelectorAll<HTMLButtonElement>("button")].find((candidate) => candidate.textContent?.includes("Open GitHub settings"));
    button?.click();
    expect(await opened).toEqual({ section: "github" });
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
    expect(element.shadowRoot.querySelector(".contribution-next")?.textContent).toContain("Use the measured result above in a Powercalc profile");
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
