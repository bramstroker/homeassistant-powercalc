import type { AppSettings, AppSettingsUpdate, Capabilities, EntityDescriptor, PowerMeterDiagnostic, SettingsSection } from "../../types";
import "./settings-view";
import type { SettingsView } from "./settings-view";
import { capabilities, defaultSettings, goodPowerMeterDiagnostic, measurementDefaults } from "../testing/test-fixtures";

interface TestCombobox extends HTMLElement {
  value: string | string[];
  options: Array<{ value: string; label: string; disabled?: boolean }>;
}

function settingsCombobox(root: ShadowRoot, name: string): TestCombobox {
  return root.querySelector(`measure-combobox[name="${name}"]`) as TestCombobox;
}

function chooseOption(picker: TestCombobox, value: string): void {
  picker.value = value;
  const input = picker.querySelector('input[slot="value"]') as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

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

describe("settings power meter test", () => {
  it("explains the meter requirements, emits a validation event, and shows diagnostic metrics", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testResult: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [{ entity_id: "sensor.plug_power", name: "Plug power", unit: "W" }];
    element.settings = { ...defaultSettings, default_power_entity_id: "sensor.plug_power" };
    document.body.append(element);
    await element.updateComplete;

    expect(element.shadowRoot.textContent).toContain("at least 0.1 W reported resolution");
    const tested = new Promise<AppSettings>((resolve) => {
      element.addEventListener("test", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    const testButton = [...element.shadowRoot.querySelectorAll("button")].find((button) => button.textContent?.includes("Validate measurement device"));
    testButton?.click();
    const detail = await tested;
    expect(detail.power_meter).toBe("hass");
    expect(detail.default_power_entity_id).toBe("sensor.plug_power");

    element.testResult = goodPowerMeterDiagnostic;
    await element.updateComplete;
    const diagnostic = element.shadowRoot.querySelector("measure-power-meter-diagnostic") as HTMLElement & { updateComplete: Promise<boolean>; shadowRoot: ShadowRoot };
    await diagnostic.updateComplete;
    expect(diagnostic.shadowRoot.textContent).toContain("12.3 W");
    expect(diagnostic.shadowRoot.textContent).toContain("2 decimals");
    expect(diagnostic.shadowRoot.textContent).toContain("1.8 s");
    expect(diagnostic.shadowRoot.textContent).toContain("Good");
  });

  it("keeps the selected meter and Shelly IP across a re-render", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testing: boolean;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = defaultSettings;
    document.body.append(element);
    await element.updateComplete;

    chooseOption(settingsCombobox(element.shadowRoot, "power_meter"), "shelly");
    await element.updateComplete;
    (element.shadowRoot.querySelector('input[name="shelly_ip"]') as HTMLInputElement).value = "10.0.0.5";

    // Simulate an app-shell re-render (e.g. the test request toggling busy state).
    element.testing = true;
    await element.updateComplete;
    element.testing = false;
    await element.updateComplete;

    expect(element.shadowRoot.querySelector('input[name="shelly_ip"]')).toBeTruthy();
    expect((element.shadowRoot.querySelector('input[name="shelly_ip"]') as HTMLInputElement).value).toBe("10.0.0.5");
  });

  it("collects the Kasa address without offering discovery", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testResult?: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = { ...defaultSettings, default_measure_device: "Kasa KP115" };
    element.testResult = goodPowerMeterDiagnostic;
    const discover = vi.fn();
    element.addEventListener("shelly-discover", discover);
    const saved = new Promise<AppSettings>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettings>).detail));
    });
    document.body.append(element);
    await element.updateComplete;

    chooseOption(settingsCombobox(element.shadowRoot, "power_meter"), "kasa");
    await element.updateComplete;
    expect(discover).not.toHaveBeenCalled();
    // Selecting a direct meter invalidates the earlier Home Assistant sensor result.
    expect(element.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();
    expect(element.shadowRoot.querySelector('measure-combobox[name="discovered_shelly"]')).toBeNull();

    const kasaIp = element.shadowRoot.querySelector('input[name="kasa_ip"]') as HTMLInputElement;
    kasaIp.value = "192.0.2.30";
    kasaIp.dispatchEvent(new Event("input"));
    await element.updateComplete;
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    const settings = await saved;
    expect(settings.power_meter).toBe("kasa");
    expect(settings.kasa_ip).toBe("192.0.2.30");
    expect(settings.shelly_ip).toBeNull();
  });

  it("discovers Shellys automatically and selects only compatible devices", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; shellyDiscoveryDevices: import("../../types").ShellyDiscoveryDevice[];
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [];
    element.settings = defaultSettings;
    const discover = vi.fn();
    element.addEventListener("shelly-discover", discover);
    document.body.append(element);
    await element.updateComplete;

    chooseOption(settingsCombobox(element.shadowRoot, "power_meter"), "shelly");
    await element.updateComplete;
    expect(discover).toHaveBeenCalledOnce();

    element.shellyDiscoveryDevices = [
      { id: "plug", name: "Kitchen plug", model: "S3PL-00112EU", generation: 3, ip_address: "10.0.0.8", supported: true, reason: null, auth_required: false },
      { id: "auth", name: "Locked plug", model: null, generation: 2, ip_address: "10.0.0.9", supported: false, reason: "Authentication is enabled; enter the Shelly password.", auth_required: true },
    ];
    await element.updateComplete;

    const discovered = settingsCombobox(element.shadowRoot, "discovered_shelly");
    expect(discovered.options[1]?.label).toContain("Kitchen plug");
    expect(discovered.options[2]?.label).toContain("Authentication is enabled");
    expect(discovered.options[2]?.disabled).toBe(false);
    chooseOption(discovered, "10.0.0.8");
    await element.updateComplete;
    expect((element.shadowRoot.querySelector('input[name="shelly_ip"]') as HTMLInputElement).value).toBe("10.0.0.8");
  });

  it("submits Shelly credentials without losing a typed password on rerender", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      settings: AppSettings; testResult?: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.settings = {
      ...defaultSettings,
      default_measure_device: "Shelly Plug",
      power_meter: "shelly",
      shelly_ip: "10.0.0.9",
      shelly_username: "admin",
      shelly_password_configured: true,
    };
    document.body.append(element);
    await element.updateComplete;

    const username = element.shadowRoot.querySelector('input[name="shelly_username"]') as HTMLInputElement;
    const password = element.shadowRoot.querySelector('input[name="shelly_password"]') as HTMLInputElement;
    username.value = "measurement";
    username.dispatchEvent(new Event("input"));
    password.value = "device-password";
    password.dispatchEvent(new Event("input"));

    element.testResult = goodPowerMeterDiagnostic;
    await element.updateComplete;
    expect((element.shadowRoot.querySelector('input[name="shelly_password"]') as HTMLInputElement).value).toBe("device-password");

    const saved = new Promise<AppSettingsUpdate>((resolve) => {
      element.addEventListener("save", (event) => resolve((event as CustomEvent<AppSettingsUpdate>).detail));
    });
    (element.shadowRoot.querySelector("form") as HTMLFormElement).requestSubmit();

    expect(await saved).toMatchObject({
      shelly_username: "measurement",
      shelly_password: "device-password",
      clear_shelly_password: false,
    });
  });

  it("renders Shelly discovery loading, empty, unavailable, and error states with refresh", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      settings: AppSettings; discoveringShellys: boolean; shellyDiscoveryAvailable?: boolean;
      shellyDiscoveryMessage?: string; shellyDiscoveryError: string;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.settings = { ...defaultSettings, power_meter: "shelly" };
    element.discoveringShellys = true;
    document.body.append(element);
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("Searching for Shelly devices");

    element.discoveringShellys = false;
    element.shellyDiscoveryAvailable = true;
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("No Shelly devices found");

    element.shellyDiscoveryAvailable = false;
    element.shellyDiscoveryMessage = "Discovery is unavailable.";
    await element.updateComplete;
    expect(element.shadowRoot.textContent).toContain("Discovery is unavailable.");

    element.shellyDiscoveryError = "Discovery request failed";
    await element.updateComplete;
    expect(element.shadowRoot.querySelector('[role="alert"]')?.textContent).toContain("Discovery request failed");
    expect([...element.shadowRoot.querySelectorAll("button")].some((button) => button.textContent?.includes("Refresh"))).toBe(true);
  });

  it("clears an earlier result when the power sensor, meter type, or Shelly address changes", async () => {
    const element = document.createElement("measure-settings-view") as HTMLElement & {
      powers: EntityDescriptor[]; settings: AppSettings; testResult?: PowerMeterDiagnostic;
      updateComplete: Promise<boolean>; shadowRoot: ShadowRoot;
    };
    element.powers = [
      { entity_id: "sensor.plug_power", name: "Plug power" },
      { entity_id: "sensor.other_power", name: "Other power" },
    ];
    element.settings = { ...defaultSettings, default_power_entity_id: "sensor.plug_power" };
    element.testResult = goodPowerMeterDiagnostic;
    const cleared = vi.fn();
    element.addEventListener("test-clear", cleared);
    document.body.append(element);
    await element.updateComplete;

    const powerSensor = element.shadowRoot.querySelector('measure-combobox[name="default_power_entity_id"]') as HTMLElement;
    powerSensor.dispatchEvent(new CustomEvent("combobox-change", {
      detail: { value: "sensor.other_power" }, bubbles: true, composed: true,
    }));
    await element.updateComplete;
    expect(element.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();

    element.testResult = goodPowerMeterDiagnostic;
    await element.updateComplete;
    chooseOption(settingsCombobox(element.shadowRoot, "power_meter"), "shelly");
    await element.updateComplete;
    expect(element.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();

    element.testResult = goodPowerMeterDiagnostic;
    await element.updateComplete;
    const shellyIp = element.shadowRoot.querySelector('input[name="shelly_ip"]') as HTMLInputElement;
    shellyIp.value = "10.0.0.7";
    shellyIp.dispatchEvent(new Event("input"));
    await element.updateComplete;
    expect(element.shadowRoot.querySelector("measure-power-meter-diagnostic")).toBeNull();
    expect(cleared).toHaveBeenCalledTimes(3);
  });
});
