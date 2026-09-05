import type { AppSettings, AppSettingsUpdate, Capabilities, EntityDescriptor, SettingsSection } from "../../types";
import "./view";
import type { SettingsView } from "./view";
import { capabilities, defaultSettings, measurementDefaults } from "../testing/fixtures";

describe("settings view", () => {
  it.each(["device", "token"] as const)("prefills and saves the contributor username after connecting with %s", async (method) => {
    const element = document.createElement("measure-settings-view") as SettingsView;
    element.settings = { ...defaultSettings, power_meter: "dummy", default_measure_device: "Test meter", default_contributor_github: null };
    document.body.append(element);
    await element.updateComplete;
    const input = element.shadowRoot!.querySelector<HTMLInputElement>('[name="default_contributor_github"]')!;
    expect(input.value).toBe("");

    element.contributionAuth = { connected: true, method, identity: { login: "octocat" } };
    await element.updateComplete;
    expect(input.value).toBe("octocat");

    const saved = new Promise<AppSettingsUpdate>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettingsUpdate>).detail));
    });
    element.shadowRoot!.querySelector<HTMLFormElement>("form")!.requestSubmit();
    expect((await saved).default_contributor_github).toBe("octocat");
  });

  it("prefills from an existing connection but preserves saved and unsaved contributor usernames", async () => {
    const element = document.createElement("measure-settings-view") as SettingsView;
    element.settings = { ...defaultSettings, default_contributor_github: null };
    element.contributionAuth = { connected: true, identity: { login: "octocat" } };
    document.body.append(element);
    await element.updateComplete;
    const input = element.shadowRoot!.querySelector<HTMLInputElement>('[name="default_contributor_github"]')!;
    expect(input.value).toBe("octocat");

    element.settings = { ...element.settings, default_contributor_github: "saved-author" };
    await element.updateComplete;
    expect(input.value).toBe("saved-author");

    element.settings = { ...element.settings, default_contributor_github: null };
    element.contributionAuth = { connected: false };
    await element.updateComplete;
    for (const value of ["unsaved-author", ""]) {
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      element.contributionAuth = { connected: true, identity: { login: "another-account" } };
      await element.updateComplete;
      expect(input.value).toBe(value);
    }
  });

  it("lists power sensors and emits the selected default on save", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[];
      settings: AppSettings;
      measureDevices: string[];
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.settings = defaultSettings;
    element.measureDevices = ["Shelly Plug S", "TP-Link Kasa KP115"];
    document.body.append(element);
    await element.updateComplete;

    const sectionButtons = [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".settings-nav button")];
    expect(sectionButtons.map((button) => button.textContent?.trim())).toEqual(["Power meter", "Profile metadata", "Measure tuning", "GitHub"]);
    expect(sectionButtons[0]?.classList.contains("active")).toBe(true);
    expect(element.shadowRoot.querySelector<HTMLElement>('[aria-labelledby="measure-tuning-title"]')?.hidden).toBe(true);

    sectionButtons[2]?.click();
    await element.updateComplete;
    expect(sectionButtons[2]?.classList.contains("active")).toBe(true);
    expect(element.shadowRoot.querySelector<HTMLElement>('[aria-labelledby="power-meter-title"]')?.hidden).toBe(true);
    expect(element.shadowRoot.querySelector<HTMLElement>('[aria-labelledby="measure-tuning-title"]')?.hidden).toBe(false);
    sectionButtons[0]?.click();
    await element.updateComplete;

    const saved = new Promise<AppSettings>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    const powerSensor = element.shadowRoot.querySelector('measure-combobox[name="default_power_entity_id"]') as HTMLElement;
    const measureDevicePicker = element.shadowRoot.querySelector('measure-combobox[name="default_measure_device"]') as HTMLElement & { updateComplete: Promise<boolean>; shadowRoot: ShadowRoot };
    const measureDevice = measureDevicePicker.shadowRoot.querySelector("input") as HTMLInputElement;
    const firmware = element.shadowRoot.querySelector('input[name="default_measure_device_firmware"]') as HTMLInputElement;
    const contributorName = element.shadowRoot.querySelector('input[name="default_contributor_name"]') as HTMLInputElement;
    const contributorGithub = element.shadowRoot.querySelector('input[name="default_contributor_github"]') as HTMLInputElement;
    const contributorEmail = element.shadowRoot.querySelector('input[name="default_contributor_email"]') as HTMLInputElement;
    firmware.value = "1.2.3";
    contributorName.value = "Test User";
    contributorGithub.value = "test-user";
    contributorEmail.value = "test@example.com";
    expect(measureDevice.required).toBe(true);
    measureDevice.focus();
    await measureDevicePicker.updateComplete;
    expect([...measureDevicePicker.shadowRoot.querySelectorAll(".option")].map((option) => option.textContent?.trim())).toEqual([
      "Shelly Plug S",
      "TP-Link Kasa KP115",
    ]);
    measureDevice.value = "shelly";
    measureDevice.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await measureDevicePicker.updateComplete;
    expect(measureDevicePicker.shadowRoot.querySelectorAll(".option")).toHaveLength(1);
    measureDevice.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    await measureDevicePicker.updateComplete;
    measureDevice.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await measureDevicePicker.updateComplete;
    expect(measureDevice.value).toBe("Shelly Plug S");
    expect(measureDevicePicker.shadowRoot.querySelector(".menu")).toBeNull();
    expect((powerSensor.shadowRoot?.querySelector("input") as HTMLInputElement).required).toBe(true);
    powerSensor.dispatchEvent(new CustomEvent("combobox-change", {
      detail: { value: "sensor.plug_power" }, bubbles: true, composed: true,
    }));
    await element.updateComplete;
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    const settings = await saved;
    expect(settings.default_power_entity_id).toBe("sensor.plug_power");
    expect(settings.default_measure_device).toBe("Shelly Plug S");
    expect(settings.default_measure_device_firmware).toBe("1.2.3");
    expect(settings.default_contributor_name).toBe("Test User");
    expect(settings.default_contributor_github).toBe("test-user");
    expect(settings.default_contributor_email).toBe("test@example.com");
    expect(settings.measurement_defaults).toEqual(measurementDefaults);
  });

  it("keeps manual measurement-device entry available when library suggestions fail", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      settings: AppSettings;
      measureDevicesError: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.settings = defaultSettings;
    element.measureDevicesError = "Library unavailable";
    document.body.append(element);
    await element.updateComplete;

    const picker = element.shadowRoot.querySelector('measure-combobox[name="default_measure_device"]') as HTMLElement & { shadowRoot: ShadowRoot };
    const input = picker.shadowRoot.querySelector("input") as HTMLInputElement;
    input.value = "My calibrated meter";

    expect(input.disabled).toBe(false);
    expect(element.shadowRoot.textContent).toContain("manual entry still works");
  });

  it("shows fast test mode only in developer mode and saves the toggle", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      settings: AppSettings;
      capabilities: Capabilities;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.settings = {
      ...defaultSettings,
      default_measure_device: "Synthetic meter",
      power_meter: "dummy",
    };
    element.capabilities = capabilities;
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('input[name="fast_test_mode"]')).toBeNull();

    element.capabilities = { ...capabilities, developer_mode: true };
    await element.updateComplete;
    const toggle = element.shadowRoot.querySelector('input[name="fast_test_mode"]') as HTMLInputElement;
    expect(toggle).not.toBeNull();
    expect(element.shadowRoot.textContent).toContain("output is not valid for contribution or real use");

    toggle.checked = true;
    const saved = new Promise<AppSettings>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect((await saved).fast_test_mode).toBe(true);
  });

  it("renders GitHub device login, token fallback, identity, and disconnect", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[];
      settings: AppSettings;
      contributionAuth: { connected: boolean; identity?: { login: string; name?: string } };
      contributionDeviceFlow: { flow_id: string; user_code: string; verification_uri: string; expires_in: number; interval: number };
      contributionDeviceStatus: { status: "pending" | "expired"; message?: string };
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = defaultSettings;
    element.contributionAuth = { connected: false };
    document.body.append(element);
    await element.updateComplete;

    [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".settings-nav button")].find((button) => button.textContent?.includes("GitHub"))?.click();
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("Connect GitHub");
    expect(element.shadowRoot.textContent).toContain("Use a personal access token instead");
    expect(element.shadowRoot.textContent).toContain("included in Home Assistant backups");
    const started = new Promise<void>((resolve) => element.addEventListener("github-device-start", () => resolve()));
    [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Connect GitHub"))?.click();
    await started;

    element.contributionDeviceFlow = {
      flow_id: "flow-1",
      user_code: "ABCD-EFGH",
      verification_uri: "https://github.com/login/device",
      expires_in: 900,
      interval: 5,
    };
    await element.updateComplete;
    expect((element.shadowRoot.querySelector(".device-code") as HTMLInputElement).value).toBe("ABCD-EFGH");
    expect(element.shadowRoot.textContent).toContain("Continue on GitHub");
    expect(element.shadowRoot.textContent).toContain("connect automatically");
    expect(element.shadowRoot.textContent).not.toContain("Check login");
    expect((element.shadowRoot.querySelector(".github-link") as HTMLAnchorElement).href).toBe("https://github.com/login/device");

    [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Copy code"))?.click();
    await vi.waitFor(() => expect(element.shadowRoot.textContent).toContain("Select the code and copy it manually"));
    expect(element.shadowRoot.textContent).not.toContain("Code copied.");

    element.contributionDeviceStatus = { status: "expired", message: "This code expired." };
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("This code expired.");
    expect(element.shadowRoot.textContent).toContain("Get a new code");

    const saved = new Promise<string>((resolve) => element.addEventListener("github-token-save", (event) => resolve((event as CustomEvent<string>).detail)));
    const token = element.shadowRoot.querySelector('input[name="github_token"]') as HTMLInputElement;
    token.value = "ghp_secret";
    [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Save token"))?.click();
    expect(await saved).toBe("ghp_secret");

    element.contributionAuth = { connected: true, identity: { login: "octocat" } };
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("octocat");
    const disconnected = new Promise<void>((resolve) => element.addEventListener("github-disconnect", () => resolve()));
    (element.shadowRoot.querySelector("button.danger") as HTMLButtonElement).click();
    await disconnected;
  });

  it("copies the device code through execCommand when the clipboard API is unavailable", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      settings: AppSettings;
      contributionAuth: { connected: boolean };
      contributionDeviceFlow: { flow_id: string; user_code: string; verification_uri: string; expires_in: number; interval: number };
      initialSection: SettingsSection;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.settings = defaultSettings;
    element.contributionAuth = { connected: false };
    element.initialSection = "github";
    element.contributionDeviceFlow = {
      flow_id: "flow-1",
      user_code: "BA41-1016",
      verification_uri: "https://github.com/login/device",
      expires_in: 900,
      interval: 5,
    };
    document.body.append(element);
    await element.updateComplete;

    // Insecure context: navigator.clipboard is not exposed at all, as inside the http ingress panel.
    const clipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    let copied = "";
    const execCommand = vi.fn(() => {
      copied = document.querySelector("textarea")?.value ?? "";
      return true;
    });
    Object.defineProperty(document, "execCommand", { value: execCommand, configurable: true });

    const copyButton = [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Copy code"));
    copyButton?.click();
    await vi.waitFor(() => expect(element.shadowRoot.textContent).toContain("Code copied."));
    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(copied).toBe("BA41-1016");
    expect(document.querySelector("textarea")).toBeNull();

    // A rejecting clipboard API (blocked by permissions policy or an unfocused document) also falls back.
    const writeText = vi.fn().mockRejectedValue(new DOMException("Write permission denied.", "NotAllowedError"));
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    execCommand.mockClear();
    copyButton?.click();
    await vi.waitFor(() => expect(execCommand).toHaveBeenCalledWith("copy"));
    expect(writeText).toHaveBeenCalledWith("BA41-1016");

    if (clipboard) Object.defineProperty(navigator, "clipboard", clipboard);
  });

  it("opens directly on the GitHub section when a section is requested", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[];
      settings: AppSettings;
      contributionAuth: { connected: boolean };
      initialSection: SettingsSection;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = defaultSettings;
    element.contributionAuth = { connected: false };
    element.initialSection = "github";
    document.body.append(element);
    await element.updateComplete;

    const githubNav = [...element.shadowRoot.querySelectorAll<HTMLButtonElement>(".settings-nav button")]
      .find((button) => button.textContent?.includes("GitHub"));
    expect(githubNav?.getAttribute("aria-current")).toBe("page");
    const githubSection = element.shadowRoot.querySelector('[aria-labelledby="github-title"]');
    expect(githubSection?.hasAttribute("hidden")).toBe(false);
  });
});
