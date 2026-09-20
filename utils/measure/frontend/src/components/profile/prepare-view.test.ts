import { ProfilePrepareView } from "./prepare-view";
import type { ProfileMeasurementFields } from "./measurement-fields";
import type { Combobox } from "../shared/combobox";
import type { StringListInput } from "../shared/string-list-input";
import type { ContributionPreview, StandbyEstimate, StandbyMeasurementResult } from "../../types";

const preview: ContributionPreview = {
  eligible: true, manufacturer_name: "Signify", manufacturer_directory: "signify", model_id: "LCT010",
  product_name: "Hue lamp", contributor: "Tester", contributor_github: "tester", measure_device: "Test meter",
  mains_voltage: 230, notes: "", device_info: {}, home_assistant: {}, device_type: "light", files: [], warnings: [],
  standby_power: 0.3, standby_power_estimated: false,
  repository: "bramstroker/homeassistant-powercalc", base_branch: "master", aliases: ["Alias"],
  commit_message: "Add profile", pr_title: "Add profile", pr_body: "Measured profile", branch_name: "measure/test",
};

async function mount(): Promise<ProfilePrepareView> {
  const element = new ProfilePrepareView();
  element.snapshot = { state: "completed", session_id: "session-1" };
  element.contributionDraft = { ...preview };
  document.body.append(element);
  await element.updateComplete;
  await element.shadowRoot!.querySelector("measure-combobox")!.updateComplete;
  return element;
}

function input(element: ProfilePrepareView, name: string): HTMLInputElement {
  return element.shadowRoot!.querySelector<HTMLInputElement>(`input[name="${name}"]`)!;
}

function submit(element: ProfilePrepareView): void {
  element.shadowRoot!.querySelector("form")!.requestSubmit();
}

async function applyEstimate(element: ProfilePrepareView): Promise<void> {
  const button = [...element.shadowRoot!.querySelectorAll<HTMLButtonElement>("button")]
    .find(button => button.textContent!.includes("Use estimated standby"))!;
  button.click();
  await element.updateComplete;
}

async function changeConnectivity(element: ProfilePrepareView, values: string[]): Promise<void> {
  const control = element.shadowRoot!.querySelector<Combobox>('[name="device_specs.connectivity"]')!;
  control.value = values;
  control.dispatchEvent(new CustomEvent("combobox-change", { bubbles: true }));
  await element.updateComplete;
}

async function mountWithConnectivity(): Promise<ProfilePrepareView> {
  const element = await mount();
  element.deviceSpecificationFields = { light: [{
    name: "connectivity", label: "Connectivity", description: "", value_type: "string",
    collection: "array", options: ["zigbee", "wifi", "bluetooth"],
  }] };
  await element.updateComplete;
  return element;
}

describe("profile validation", () => {
  it.each(["connectivity", "manufacturer"])("warns after changing %s without recalculating on validation", async field => {
    const element = await mountWithConnectivity();
    await applyEstimate(element);
    if (field === "connectivity") {
      await changeConnectivity(element, ["zigbee"]);
    } else {
      const manufacturer = element.shadowRoot!.querySelector<Combobox>('[name="manufacturer_name"]')!;
      manufacturer.value = "Acme";
      manufacturer.dispatchEvent(new CustomEvent("combobox-change", { bubbles: true }));
      await element.updateComplete;
    }

    const warning = () => element.shadowRoot!.querySelector('.standby-field [role="alert"]');
    expect(warning()?.textContent).toContain("Your standby value has not been updated");
    expect(input(element, "standby_power").value).toBe("0.4");
    const onPreview = vi.fn();
    element.addEventListener("contribution-preview", onPreview);
    submit(element);
    expect(onPreview.mock.lastCall![0].detail).toMatchObject({ standby_power: 0.4, standby_power_estimated: true });
    element.contributionPreview = { ...preview, ...onPreview.mock.lastCall![0].detail };
    await element.updateComplete;
    expect(warning()).not.toBeNull();

    await applyEstimate(element);
    expect(warning()).toBeNull();
  });

  it("warns while a new suggestion loads and clears the warning when applying it", async () => {
    const element = await mountWithConnectivity();
    await applyEstimate(element);
    let resolve!: (estimate: StandbyEstimate) => void;
    element.loadStandbyEstimate = vi.fn(() => new Promise<StandbyEstimate>(done => { resolve = done; }));
    await changeConnectivity(element, ["wifi"]);
    expect(element.shadowRoot!.querySelector('.standby-field [role="alert"]')).not.toBeNull();
    expect(element.shadowRoot!.textContent).toContain("Loading standby suggestion");
    resolve({ power_w: 0.7, basis: "connectivity", profile_count: 4 });
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Use estimated standby: 0.7 W"));
    expect(input(element, "standby_power").value).toBe("0.4");
    await applyEstimate(element);
    expect(input(element, "standby_power").value).toBe("0.7");
    expect(element.shadowRoot!.querySelector('.standby-field [role="alert"]')).toBeNull();
  });

  it.each(["manual", "uncheck", "measured", "session"])("clears an outdated estimate warning after %s standby replacement", async action => {
    const element = await mountWithConnectivity();
    await applyEstimate(element);
    await changeConnectivity(element, ["wifi"]);
    expect(element.shadowRoot!.querySelector('.standby-field [role="alert"]')).not.toBeNull();
    if (action === "manual") {
      input(element, "standby_power").value = "0.8";
      input(element, "standby_power").dispatchEvent(new Event("input", { bubbles: true }));
    } else if (action === "uncheck") {
      input(element, "standby_power_estimated").checked = false;
      input(element, "standby_power_estimated").dispatchEvent(new Event("change", { bubbles: true }));
    } else if (action === "measured") {
      element.measureStandby = vi.fn().mockResolvedValue({ status: "measured", power_w: 0.65 });
      element.shadowRoot!.querySelector("measure-profile-measurement-fields")!.dispatchEvent(new CustomEvent("standby-measure", { bubbles: true }));
      await vi.waitFor(() => expect(input(element, "standby_power").value).toBe("0.65"));
    } else {
      element.snapshot = { state: "completed", session_id: "session-2" };
    }
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector('.standby-field [role="alert"]')).toBeNull();
  });

  it("does not warn before applying an estimate, for reordered connectivity, or after reverting a change", async () => {
    const element = await mountWithConnectivity();
    await changeConnectivity(element, ["zigbee", "bluetooth"]);
    expect(element.shadowRoot!.querySelector('.standby-field [role="alert"]')).toBeNull();
    await applyEstimate(element);
    await changeConnectivity(element, ["bluetooth", "zigbee"]);
    expect(element.shadowRoot!.querySelector('.standby-field [role="alert"]')).toBeNull();
    await changeConnectivity(element, ["wifi"]);
    expect(element.shadowRoot!.querySelector('.standby-field [role="alert"]')).not.toBeNull();
    await changeConnectivity(element, ["zigbee", "bluetooth"]);
    expect(element.shadowRoot!.querySelector('.standby-field [role="alert"]')).toBeNull();
  });

  it("keeps measurement guidance accessible when the description fails validation", async () => {
    const element = await mount();
    const description = element.shadowRoot!.querySelector<HTMLTextAreaElement>('textarea[name="measure_description"]')!;
    const hint = element.shadowRoot!.querySelector("#measure_description-hint")!;
    expect(description.getAttribute("aria-describedby")).toBe(hint.id);

    description.value = "a".repeat(2001);
    submit(element);
    await element.updateComplete;
    await element.shadowRoot!.querySelector<ProfileMeasurementFields>("measure-profile-measurement-fields")!.updateComplete;

    expect(description.getAttribute("aria-invalid")).toBe("true");
    expect(description.getAttribute("aria-describedby")).toBe("measure_description-hint measure_description-error");
    expect(hint.textContent).toContain("measurement setup, device settings, or test conditions");
    expect(element.shadowRoot!.querySelector("#measure_description-error")!.textContent).toContain("2000");
  });

  it("applies a retry result, clears estimated, and requires validation again", async () => {
    const element = await mount();
    let resolve!: (result: StandbyMeasurementResult) => void;
    element.measureStandby = vi.fn(() => new Promise<StandbyMeasurementResult>(done => { resolve = done; }));
    element.contributionFormValues = { standby_power: "0.4", standby_power_estimated: "true" };
    await element.updateComplete;
    const fields = element.shadowRoot!.querySelector("measure-profile-measurement-fields")!;
    fields.dispatchEvent(new CustomEvent("standby-measure", { bubbles: true }));
    await element.updateComplete;
    expect(element.measureStandby).toHaveBeenCalledWith("session-1");
    expect(element.shadowRoot!.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);
    resolve({ status: "measured", power_w: 0.65 });
    await vi.waitFor(() => expect(input(element, "standby_power").value).toBe("0.65"));
    expect(input(element, "standby_power_estimated").checked).toBe(false);
    expect(element.previewDirty).toBe(true);
  });

  it.each(["unavailable", "error", "stale"])("preserves entered standby after a %s retry", async outcome => {
    const element = await mount();
    let resolve!: (result: StandbyMeasurementResult) => void;
    let reject!: (error: Error) => void;
    element.measureStandby = vi.fn(() => new Promise<StandbyMeasurementResult>((done, fail) => { resolve = done; reject = fail; }));
    element.shadowRoot!.querySelector("measure-profile-measurement-fields")!.dispatchEvent(new CustomEvent("standby-measure", { bubbles: true }));
    if (outcome === "stale") element.snapshot = { state: "completed", session_id: "session-2" };
    if (outcome === "error") reject(new Error("Meter offline"));
    else resolve({ status: outcome === "stale" ? "measured" : "unavailable", power_w: outcome === "stale" ? 0.9 : null });
    await Promise.resolve();
    await element.updateComplete;
    expect(input(element, "standby_power").value).toBe("0.3");
  });

  it("allows standby overrides for non-light profiles and preserves omitted values", async () => {
    const element = await mount();
    element.contributionDraft = { ...preview, device_type: "fan", standby_power: null };
    const onPreview = vi.fn();
    element.addEventListener("contribution-preview", onPreview);
    await element.updateComplete;
    submit(element);
    expect(onPreview.mock.lastCall![0].detail).not.toHaveProperty("standby_power");
    input(element, "standby_power").value = "1.2";
    input(element, "standby_power_estimated").checked = true;
    submit(element);
    expect(onPreview.mock.lastCall![0].detail).toMatchObject({ standby_power: 1.2, standby_power_estimated: true });
  });
  it("requires a correction for legacy zero standby and applies estimates only on request", async () => {
    const element = await mount();
    element.contributionDraft = { ...preview, standby_power: null };
    await element.updateComplete;
    const onPreview = vi.fn();
    element.addEventListener("contribution-preview", onPreview);
    submit(element);
    await element.updateComplete;
    expect(onPreview).not.toHaveBeenCalled();
    expect(input(element, "standby_power").getAttribute("aria-invalid")).toBe("true");
    await vi.waitFor(() => expect(element.shadowRoot!.activeElement).toBe(input(element, "standby_power")));
    expect(input(element, "standby_power").value).toBe("");
    const apply = [...element.shadowRoot!.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent!.includes("Use estimated standby"))!;
    apply.click();
    await element.updateComplete;
    expect(input(element, "standby_power").value).toBe("0.4");
    expect(input(element, "standby_power_estimated").checked).toBe(true);
    expect(element.previewDirty).toBe(true);
    submit(element);
    expect(onPreview.mock.calls[0]![0].detail).toMatchObject({ standby_power: 0.4, standby_power_estimated: true });

    input(element, "standby_power").value = "0.05";
    input(element, "standby_power").dispatchEvent(new Event("input", { bubbles: true }));
    input(element, "standby_power_estimated").checked = false;
    input(element, "standby_power_estimated").dispatchEvent(new Event("change", { bubbles: true }));
    await element.updateComplete;
    submit(element);
    expect(onPreview.mock.lastCall![0].detail).toMatchObject({ standby_power: 0.05, standby_power_estimated: false });
  });

  it("refreshes suggestions without overwriting edits and ignores stale responses", async () => {
    const element = await mount();
    let resolveFirst!: (estimate: StandbyEstimate) => void;
    let resolveSecond!: (estimate: StandbyEstimate) => void;
    const loader = vi.fn()
      .mockImplementationOnce(() => new Promise<StandbyEstimate>(resolve => { resolveFirst = resolve; }))
      .mockImplementationOnce(() => new Promise<StandbyEstimate>(resolve => { resolveSecond = resolve; }));
    element.loadStandbyEstimate = loader;
    element.contributionDraft = { ...preview, device_specs: { connectivity: ["zigbee"] } };
    await element.updateComplete;
    element.contributionFormValues = { manufacturer_name: "Acme", standby_power: "0.8", standby_power_estimated: "false", "device_specs.connectivity": ["wifi"] };
    await element.updateComplete;
    expect(loader).toHaveBeenLastCalledWith("Acme", ["wifi"]);
    resolveSecond({ power_w: 0.5, basis: "manufacturer", profile_count: 3 });
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Use estimated standby: 0.5 W"));
    resolveFirst({ power_w: 0.2, basis: "connectivity", profile_count: 5 });
    await Promise.resolve();
    await element.updateComplete;
    expect(element.shadowRoot!.textContent).toContain("Use estimated standby: 0.5 W");
    expect(input(element, "standby_power").value).toBe("0.8");
    expect(input(element, "standby_power_estimated").checked).toBe(false);
  });

  it("offers a fallback after a library outage but only suggests estimates for lights", async () => {
    const element = await mount();
    element.loadStandbyEstimate = vi.fn().mockRejectedValue(new Error("offline"));
    element.contributionDraft = { ...preview, device_specs: { connectivity: ["wifi"] } };
    await vi.waitFor(() => expect(element.shadowRoot!.textContent).toContain("Use estimated standby: 0.4 W"));
    element.contributionDraft = { ...preview, device_type: "generic" };
    await element.updateComplete;
    expect(input(element, "standby_power")).not.toBeNull();
    expect(element.shadowRoot!.textContent).not.toContain("Use estimated standby");
  });

  it("marks required fields, lists missing values together and focuses the first error", async () => {
    const element = await mount();
    const onPreview = vi.fn();
    element.addEventListener("contribution-preview", onPreview);
    input(element, "model_id").value = " ";
    input(element, "product_name").value = "";
    const manufacturer = element.shadowRoot!.querySelector("measure-combobox")!;
    manufacturer.value = "";
    await manufacturer.updateComplete;
    submit(element);
    await element.updateComplete;
    await manufacturer.updateComplete;

    expect(onPreview).not.toHaveBeenCalled();
    expect(element.shadowRoot!.querySelectorAll(".validation-summary li")).toHaveLength(3);
    expect(input(element, "model_id").parentElement!.querySelector(".required-marker")).not.toBeNull();
    expect(input(element, "product_url").parentElement!.querySelector(".required-marker")).toBeNull();
    expect(input(element, "model_id").getAttribute("aria-invalid")).toBe("true");
    expect(input(element, "model_id").getAttribute("aria-describedby")).toBe("model_id-error");
    expect(manufacturer.shadowRoot!.querySelector("input")!.getAttribute("aria-invalid")).toBe("true");
    await vi.waitFor(() => expect(manufacturer.shadowRoot!.activeElement).toBe(manufacturer.shadowRoot!.querySelector("input")));
    const link = [...element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".validation-summary button")].find((button) => button.textContent!.includes("Product name"))!;
    link.click();
    expect(element.shadowRoot!.activeElement).toBe(input(element, "product_name"));

    input(element, "product_name").value = "Corrected name";
    input(element, "product_name").dispatchEvent(new Event("input", { bubbles: true }));
    await element.updateComplete;
    expect(input(element, "product_name").getAttribute("aria-invalid")).toBe("false");
    expect(element.shadowRoot!.querySelectorAll(".validation-summary li")).toHaveLength(2);
  });

  it("offers only 120 V and 230 V when no measured voltage range is available", async () => {
    const element = await mount();
    const mainsVoltage = element.shadowRoot!.querySelector('measure-combobox[name="mains_voltage"]') as Combobox;

    expect(mainsVoltage.value).toBe("230");
    expect(mainsVoltage.options).toEqual([
      { value: "120", label: "120 V" },
      { value: "230", label: "230 V" },
    ]);
  });

  it("requires a fresh preview after edits and displays normalized server values", async () => {
    const element = await mount();
    element.contributionPreview = { ...preview };
    await element.updateComplete;
    const aliases = element.shadowRoot!.querySelector<StringListInput>('measure-string-list-input[name="aliases"]')!;
    aliases.value = [" Alias ", "Second alias"];
    aliases.dispatchEvent(new CustomEvent("list-input-change", { bubbles: true, composed: true }));
    await element.updateComplete;
    expect(element.shadowRoot!.textContent).toContain("Your changes have not been validated yet");
    expect(element.shadowRoot!.querySelector<HTMLButtonElement>('button[type="submit"]')?.textContent).toContain("Validate changes");
    expect(element.shadowRoot!.querySelector(".validation-status.valid")).toBeNull();
    expect(element.shadowRoot!.querySelector(".prepared-preview")).toBeNull();
    expect(element.shadowRoot!.textContent).not.toContain("Continue to submit profile");
    const onPreview = vi.fn();
    element.addEventListener("contribution-preview", onPreview);
    submit(element);
    expect(onPreview.mock.calls[0]![0].detail.aliases).toEqual(["Alias", "Second alias"]);
    element.contributionBusy = true;
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector("fieldset")!.disabled).toBe(true);
    element.contributionPreview = { ...preview };
    element.contributionBusy = false;
    await element.updateComplete;
    const normalizedAliases = element.shadowRoot!.querySelector<StringListInput>('measure-string-list-input[name="aliases"]')!;
    expect(normalizedAliases.value).toEqual(["Alias"]);
  });

  it("preserves boolean and enum specification values and highlights schema errors on the exact field", async () => {
    const element = await mount();
    element.deviceSpecificationFields = { light: [
      { name: "dimmable", label: "Dimmable", description: "Supports dimming", value_type: "boolean", collection: "scalar", options: [] },
      { name: "color_mode", label: "Color mode", description: "", value_type: "string", collection: "scalar", options: ["rgb", "white"] },
    ] };
    element.contributionDraft = { ...preview, device_specs: { dimmable: false, color_mode: "rgb" } };
    await element.updateComplete;
    const select = element.shadowRoot!.querySelector('measure-combobox[name="device_specs.dimmable"]') as Combobox;
    expect(select.value).toBe("false");
    expect((element.shadowRoot!.querySelector('measure-combobox[name="device_specs.color_mode"]') as Combobox).value).toBe("rgb");
    const onPreview = vi.fn();
    element.addEventListener("contribution-preview", onPreview);
    submit(element);
    expect(onPreview.mock.calls[0]![0].detail.device_specs).toEqual({ dimmable: false, color_mode: "rgb" });
    element.contributionError = "Choose a supported color mode.";
    element.contributionErrorField = "device_specs.color_mode";
    await element.updateComplete;
    const colorMode = element.shadowRoot!.querySelector('measure-combobox[name="device_specs.color_mode"]') as Combobox;
    await colorMode.updateComplete;
    expect(colorMode.shadowRoot!.querySelector("input")!.getAttribute("aria-invalid")).toBe("true");
    await vi.waitFor(() => expect(colorMode.shadowRoot!.activeElement).toBe(colorMode.shadowRoot!.querySelector("input")));
    expect(element.shadowRoot!.querySelector(".validation-summary")!.textContent).toContain("Color mode: Choose a supported color mode.");
  });

  it("always shows server errors even when their field is not editable", async () => {
    const element = await mount();
    element.contributionError = "Generated calculation strategy is invalid.";
    element.contributionErrorField = "calculation_strategy";
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector(".validation-summary")!.textContent).toContain(element.contributionError);
    await vi.waitFor(() => expect(element.shadowRoot!.activeElement).toBe(element.shadowRoot!.querySelector(".validation-summary")));
  });
});
