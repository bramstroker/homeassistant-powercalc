import type { ContributionPreview, SessionSnapshot } from "../../types";
import "./profile-prepare-view";
import "./profile-use-view";

describe("profile flow components", () => {
  it("defaults to the GitHub method for an eligible draft and offers manual as an alternative", async () => {
    let element = document.createElement("measure-profile-prepare-view") as HTMLElement & {
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
        contributor_github?: string;
        contributor_email?: string;
        device_specs?: Record<string, unknown> | null;
        device_type?: string;
        measure_device?: string;
        mains_voltage?: number;
        voltage_range?: { min: number; max: number };
        device_info: Record<string, string>;
        home_assistant: Record<string, string>;
        notes: string;
        files: { path: string; rendered_json: Record<string, string> }[];
        model_json: Record<string, string>;
        commit_message: string;
        pr_title: string;
        pr_body: string;
        branch_name: string;
        job_id?: string;
        warnings: string[];
      };
      contributionResult: { status: string; pull_request_url: string };
      manufacturers: string[];
      measureDevices: string[];
      deviceSpecificationFields: Record<string, { name: string; label: string; description: string; value_type: "string" | "number" | "integer" | "boolean"; collection: "scalar" | "array" | "scalar_or_array"; options: string[] }[]>;
      preparedProfileUrl: (jobId: string) => string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.snapshot = { state: "completed" };
    element.files = [{ name: "model.json", size: 5678, media_type: "application/json" }];
    element.fileUrl = (name) => `/download/${name}`;
    element.downloadAll = () => {};
    element.contributionAuth = { connected: true, identity: { login: "octocat" } };
    element.manufacturers = ["IKEA", "Signify"];
    element.measureDevices = ["Shelly Plug S", "Shelly PM Mini Gen3"];
    element.deviceSpecificationFields = {
      light: [
        { name: "rated_power", label: "Rated power", description: "Rated watts", value_type: "number", collection: "scalar", options: [] },
        { name: "connectivity", label: "Connectivity", description: "Communication protocols", value_type: "string", collection: "array", options: ["zigbee", "wifi"] },
      ],
    };
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
      contributor_github: "octocat",
      device_specs: { rated_power: 9.5, connectivity: ["zigbee"] },
      device_type: "light",
      measure_device: "Shelly PM Mini Gen3",
      mains_voltage: 230,
      voltage_range: { min: 229.9, max: 231.2 },
      device_info: { device: "light.desk" },
      home_assistant: { version: "2026.7" },
      notes: "Measured through the HA app.",
      files: [{ path: "profile_library/signify/LCT010/model.json", rendered_json: { name: "Hue lamp" } }],
      model_json: { name: "Hue lamp", device_type: "light" },
      commit_message: "Add Signify LCT010",
      pr_title: "Add Signify LCT010",
      pr_body: "Adds a measured profile.",
      branch_name: "measure/signify-lct010",
      job_id: "job-1",
      warnings: [],
    };
    element.preparedProfileUrl = (jobId) => `/prepared/${jobId}.zip`;
    element.contributionResult = { status: "success", pull_request_url: "https://github.com/bramstroker/homeassistant-powercalc/pull/1" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector(".download-all")).toBeNull();
    expect(element.shadowRoot.querySelectorAll(".method-card")).toHaveLength(0);
    const preparation = element.shadowRoot.querySelector(".profile-metadata > .contribution-auto");
    expect(preparation?.textContent).toContain("profile_library/signify/LCT010/model.json");
    expect(preparation?.textContent).toContain("Profile validated");
    expect(preparation?.querySelector<HTMLDetailsElement>(".prepared-preview")?.open).toBe(false);
    expect(preparation?.querySelector(".prepared-preview summary")?.textContent).toBe("Prepared files (1)");
    expect(preparation?.querySelector<HTMLDetailsElement>(".profile-details")?.open).toBe(false);
    expect(preparation?.textContent).not.toContain("Device device");
    expect(preparation?.textContent).not.toContain("Connected to GitHub as octocat");
    expect(preparation?.textContent).not.toContain("Add Signify LCT010");
    expect(preparation?.textContent).not.toContain('"aliases"');
    expect(element.shadowRoot.textContent).not.toContain("Connected to GitHub as octocat");
    expect(element.shadowRoot.textContent).not.toContain("Add Signify LCT010");
    expect(element.shadowRoot.querySelectorAll('input[name="model_id"]')).toHaveLength(1);
    const manufacturerLink = element.shadowRoot.querySelector(".manufacturer-library-link") as HTMLAnchorElement;
    expect(manufacturerLink.href).toBe("https://library.powercalc.nl/manufacturers/signify");
    expect(element.shadowRoot.textContent).toContain("without repeating the manufacturer");
    expect(element.shadowRoot.textContent).toContain("match the naming and metadata patterns used there");
    const manufacturerPicker = element.shadowRoot.querySelector('measure-combobox[name="manufacturer_name"]') as HTMLElement & {
      allowCustom: boolean;
      options: { value: string }[];
    };
    expect(manufacturerPicker.allowCustom).toBe(true);
    expect(manufacturerPicker.options.map((option) => option.value)).toEqual(["IKEA", "Signify"]);
    const measureDevicePicker = element.shadowRoot.querySelector('measure-combobox[name="measure_device"]') as HTMLElement & {
      allowCustom: boolean;
      value: string;
      options: { value: string }[];
    };
    expect(measureDevicePicker.allowCustom).toBe(true);
    expect(measureDevicePicker.value).toBe("Shelly PM Mini Gen3");
    expect(measureDevicePicker.options.map((option) => option.value)).toEqual(["Shelly Plug S", "Shelly PM Mini Gen3"]);
    expect(element.shadowRoot.querySelector('measure-combobox[name="mains_voltage"]')).toBeNull();
    expect(element.shadowRoot.textContent).toContain("Calculated from the measured 229.9–231.2 V range");
    expect(element.shadowRoot.querySelector('button[type="submit"]')).toBeNull();
    const nextButton = element.shadowRoot.querySelector<HTMLButtonElement>(".validation-footer button.primary");
    expect(nextButton?.textContent).toContain("Continue to use profile");
    const onShare = vi.fn();
    element.addEventListener("share", onShare);
    nextButton?.click();
    expect(onShare).toHaveBeenCalledOnce();

    const connectivity = element.shadowRoot.querySelector('measure-combobox[name="device_specs.connectivity"]') as HTMLElement & {
      value: string[];
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    expect(connectivity.value).toEqual(["zigbee"]);
    await connectivity.updateComplete;
    const connectivityInput = connectivity.shadowRoot.querySelector("input") as HTMLInputElement;
    connectivityInput.value = "wifi";
    connectivityInput.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await connectivity.updateComplete;
    connectivityInput.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    await connectivity.updateComplete;
    connectivityInput.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await connectivity.updateComplete;
    expect(connectivity.value).toEqual(["zigbee", "wifi"]);

    const previewed = new Promise<unknown>((resolve) => element.addEventListener("contribution-preview", (event) => resolve((event as CustomEvent).detail)));
    (element.shadowRoot.querySelector(".contribution-form") as HTMLFormElement).requestSubmit();
    expect(await previewed).toMatchObject({
      manufacturer_name: "Signify",
      device_specs: { rated_power: 9.5, connectivity: ["zigbee", "wifi"] },
    });

    // The backend responds with a newly validated, normalized preview.
    element.contributionPreview = { ...element.contributionPreview, device_specs: { rated_power: 9.5, connectivity: ["zigbee", "wifi"] } };

    const useElement = document.createElement("measure-profile-use-view") as typeof element;
    useElement.snapshot = element.snapshot;
    useElement.contributionAuth = element.contributionAuth;
    useElement.contributionPreview = element.contributionPreview;
    useElement.contributionResult = element.contributionResult;
    useElement.preparedProfileUrl = element.preparedProfileUrl;
    element.replaceWith(useElement);
    element = useElement;
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("Choose how to use the profile");
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
    expect(element.shadowRoot.textContent).toContain("Connected to GitHub as octocat");
    expect(element.shadowRoot.textContent).toContain("Add Signify LCT010");

    const submit = [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".contribution-auto button.primary")]
      .find((button) => button.textContent?.includes("Confirm and open PR")) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    (element.shadowRoot.querySelector('input[name="confirm_contribution"]') as HTMLInputElement).click();
    await element.updateComplete;
    expect(submit.disabled).toBe(false);
    const submitted = new Promise<unknown>((resolve) => element.addEventListener("contribution-submit", (event) => resolve((event as CustomEvent).detail)));
    submit.click();
    expect(await submitted).toMatchObject({ confirmed: true, manufacturer_name: "Signify" });
    expect((element.shadowRoot.querySelector(".success-link") as HTMLAnchorElement).href).toBe(element.contributionResult.pull_request_url);

    // Switching delivery method keeps the shared profile metadata and preview in place.
    manualCard.click();
    await element.updateComplete;
    expect(element.shadowRoot.querySelector(".profile-delivery")).toBeTruthy();
    expect(element.shadowRoot.querySelector(".auth-shortcut")).toBeNull();
    expect(element.shadowRoot.querySelector(".contribution-next")?.textContent).toContain("Read the contribution guide");
    const preparedDownload = element.shadowRoot.querySelector(".contribution-next a[download]") as HTMLAnchorElement;
    expect(preparedDownload.getAttribute("href")).toBe("/prepared/job-1.zip");
  });

  it("shows product-name contribution errors beside the naming guidance", async () => {
    const element = document.createElement("measure-profile-prepare-view") as HTMLElement & {
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
      contributor: "octocat", contributor_github: "octocat", measure_device: "Test meter",
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
    const element = document.createElement("measure-profile-use-view") as HTMLElement & {
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
});
