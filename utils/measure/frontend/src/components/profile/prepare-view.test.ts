import { ProfilePrepareView } from "./prepare-view";
import type { Combobox } from "../shared/combobox";
import type { ContributionPreview } from "../../types";

const preview: ContributionPreview = {
  eligible: true, manufacturer_name: "Signify", manufacturer_directory: "signify", model_id: "LCT010",
  product_name: "Hue lamp", contributor: "Tester", contributor_github: "tester", measure_device: "Test meter",
  mains_voltage: 230, notes: "", device_info: {}, home_assistant: {}, device_type: "light", files: [], warnings: [],
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

describe("profile validation", () => {
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
    input(element, "aliases").value = "Alias, Alias";
    input(element, "aliases").dispatchEvent(new Event("input", { bubbles: true }));
    await element.updateComplete;
    expect(element.shadowRoot!.textContent).toContain("Your changes have not been validated yet");
    expect(element.shadowRoot!.querySelector<HTMLButtonElement>('button[type="submit"]')?.textContent).toContain("Validate changes");
    expect(element.shadowRoot!.querySelector(".validation-status.valid")).toBeNull();
    expect(element.shadowRoot!.querySelector(".prepared-preview")).toBeNull();
    expect(element.shadowRoot!.textContent).not.toContain("Continue to use profile");
    submit(element);
    element.contributionBusy = true;
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector("fieldset")!.disabled).toBe(true);
    element.contributionPreview = { ...preview };
    element.contributionBusy = false;
    await element.updateComplete;
    expect(input(element, "aliases").value).toBe("Alias");
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
    element.contributionErrorField = "standby_power";
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector(".validation-summary")!.textContent).toContain(element.contributionError);
    await vi.waitFor(() => expect(element.shadowRoot!.activeElement).toBe(element.shadowRoot!.querySelector(".validation-summary")));
  });
});
