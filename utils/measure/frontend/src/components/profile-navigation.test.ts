import type { AppSettings, ContributionPreview } from "../types";
import { AppShell } from "./app-shell";
import type { Combobox } from "./combobox";
import type { ResultView } from "./result-view";
import { capabilities, controllerOf, defaultSettings } from "./test-fixtures";

const draft: ContributionPreview = {
  eligible: true, manufacturer_name: "Signify", manufacturer_directory: "signify", model_id: "LCT010",
  product_name: "Hue lamp", contributor: "", contributor_github: "tester", measure_device: "Test meter",
  mains_voltage: 230, notes: "", device_info: {}, home_assistant: {}, device_type: "light", files: [], warnings: [],
  repository: "bramstroker/homeassistant-powercalc", base_branch: "master", commit_message: "Add profile",
  pr_title: "Add profile", pr_body: "Measured profile", branch_name: "measure/test",
};

function view(app: AppShell): ResultView {
  return app.shadowRoot!.querySelector("measure-result-view")!;
}

function field(app: AppShell, name: string): HTMLInputElement {
  return view(app).shadowRoot!.querySelector(`[name="${name}"]`)!;
}

async function rendered(app: AppShell): Promise<void> {
  await app.updateComplete;
  await view(app).updateComplete;
}

async function mount(preview?: ContributionPreview) {
  vi.spyOn(AppShell.prototype as unknown as { boot: () => Promise<void> }, "boot").mockResolvedValue();
  const app = new AppShell();
  app.snapshot = { state: "completed", session_id: "session-1" };
  app.view = "profile";
  app.settings = defaultSettings;
  app.contributionDraft = { ...draft };
  app.contributionPreview = preview;
  app.deviceSpecificationFields = { light: [{
    name: "connectivity", label: "Connectivity", description: "", value_type: "string",
    collection: "array", options: ["zigbee", "wifi"],
  }] };
  const api = {
    diagnosticsUrl: () => "/diagnostics",
    getMeasureDevices: vi.fn(async () => ({ devices: [] })),
    saveSettings: vi.fn(async (settings: AppSettings) => settings),
    getCapabilities: vi.fn(async () => capabilities),
    getDummyLoadCalibration: vi.fn(async () => null),
    getContributionDraft: vi.fn(async () => ({ ...draft })),
    previewContribution: vi.fn(async () => ({ ...draft, contributor: "Tester" })),
  };
  (app as unknown as { api: unknown }).api = api;
  document.body.append(app);
  await rendered(app);
  return { app, api, controller: controllerOf(app) };
}

async function edit(app: AppShell, name: string, value: string): Promise<void> {
  const control = field(app, name);
  control.value = value;
  control.dispatchEvent(new Event("input", { bubbles: true }));
  await rendered(app);
}

async function backAndForward(app: AppShell): Promise<void> {
  controllerOf(app).backToResult();
  await app.updateComplete;
  controllerOf(app).openProfile();
  await rendered(app);
}

afterEach(() => document.body.replaceChildren());

describe("profile draft navigation", () => {
  it("keeps unfinished text, empty overrides and multiselect tags when returning from Result", async () => {
    const { app } = await mount();
    await edit(app, "product_name", "Edited product ");
    await edit(app, "aliases", "First alias, ");
    await edit(app, "contributor_github", "");
    const connectivity = field(app, "device_specs.connectivity") as unknown as Combobox;
    connectivity.value = ["zigbee", "wifi"];
    connectivity.dispatchEvent(new CustomEvent("combobox-change", { bubbles: true }));
    await rendered(app);

    await backAndForward(app);

    expect(field(app, "product_name").value).toBe("Edited product ");
    expect(field(app, "aliases").value).toBe("First alias, ");
    expect(field(app, "contributor_github").value).toBe("");
    expect(field(app, "device_specs.connectivity").value).toEqual(["zigbee", "wifi"]);
    expect(view(app).previewDirty).toBe(true);
  });

  it("does not treat edits as validated after remounting an existing preview", async () => {
    const { app, controller } = await mount({ ...draft, contributor: "Tester" });
    await edit(app, "product_name", "Updated lamp");
    await backAndForward(app);

    expect(view(app).previewDirty).toBe(true);
    controller.openShare();
    expect(app.view).toBe("profile");

    await controller.previewContribution({ ...draft, contributor: "Tester", product_name: "Updated lamp" });
    await rendered(app);
    expect(app.contributionFormValues).toBeUndefined();
    expect(view(app).previewDirty).toBe(false);
    controller.openShare();
    expect(app.view).toBe("share");
  });

  it("discards session drafts when starting a new measurement", async () => {
    const { app, controller } = await mount();
    await edit(app, "product_name", "Only this session");
    controller.newMeasurement();
    expect(app.contributionFormValues).toBeUndefined();
  });
});

describe("profile defaults after saving settings", () => {
  it("refreshes untouched contributor and firmware fields while retaining unfinished edits", async () => {
    const { app, api, controller } = await mount();
    await edit(app, "product_name", "Edited lamp");
    api.getContributionDraft.mockResolvedValue({ ...draft, contributor: "Saved contributor", contributor_email: "saved@example.com", measure_device_firmware: "1.2" });
    controller.openSettings("profile");
    await app.updateComplete;
    await controller.saveSettings({ ...defaultSettings, default_contributor_name: "Saved contributor" });
    await rendered(app);

    expect(field(app, "contributor").value).toBe("Saved contributor");
    expect(field(app, "contributor_email").value).toBe("saved@example.com");
    expect(field(app, "measure_device_firmware").value).toBe("1.2");
    expect(field(app, "product_name").value).toBe("Edited lamp");
  });

  it("retains explicit overrides, including cleared fields, across validation and settings saves", async () => {
    const { app, api, controller } = await mount();
    await edit(app, "contributor", "Profile author");
    await edit(app, "contributor_email", "");
    api.previewContribution.mockResolvedValue({ ...draft, contributor: "Profile author", contributor_email: "" });
    await controller.previewContribution({ ...draft, contributor: "Profile author", contributor_email: "" });
    await rendered(app);
    const preview = app.contributionPreview;
    api.getContributionDraft.mockResolvedValue({ ...draft, contributor: "Default author", contributor_email: "default@example.com" });
    controller.openSettings("profile");
    await app.updateComplete;
    await controller.saveSettings(defaultSettings);
    await rendered(app);

    expect(field(app, "contributor").value).toBe("Profile author");
    expect(field(app, "contributor_email").value).toBe("");
    expect(app.contributionPreview).toBe(preview);
  });

  it("returns from Use profile to Prepare if updated defaults invalidate the preview", async () => {
    const { app, api, controller } = await mount({ ...draft, product_name: "Validated name" });
    controller.openShare();
    await rendered(app);
    controller.openSettings("profile");
    await app.updateComplete;
    api.getContributionDraft.mockResolvedValue({ ...draft, contributor: "New default" });
    await controller.saveSettings(defaultSettings);
    await rendered(app);

    expect(app.view).toBe("profile");
    expect(app.contributionPreview).toBeUndefined();
    expect(field(app, "product_name").value).toBe("Validated name");
    expect(field(app, "contributor").value).toBe("New default");
  });
});
