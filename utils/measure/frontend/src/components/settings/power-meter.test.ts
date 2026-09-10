import type { AppSettings, AppSettingsUpdate, EntityDescriptor, PowerMeterDiagnostic } from "../../types";
import "./view";
import { defaultSettings, goodPowerMeterDiagnostic } from "../testing/fixtures";
import { chooseOption, settingsCombobox } from "./test-helpers";

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
